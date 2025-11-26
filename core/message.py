import json
import time
import asyncio
import threading
import logging
import websocket
from dataclasses import dataclass
from typing import Optional, Dict, Callable, Any
from queue import Queue
from enum import Enum
from collections import OrderedDict

logging.basicConfig(
    level=logging.ERROR,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("MessageHandler")

class GatewayOpcode(Enum):
    """Discord Gateway Opcodes"""
    DISPATCH = 0
    HEARTBEAT = 1
    IDENTIFY = 2
    PRESENCE_UPDATE = 3
    VOICE_STATE_UPDATE = 4
    RESUME = 6
    RECONNECT = 7
    REQUEST_GUILD_MEMBERS = 8
    INVALID_SESSION = 9
    HELLO = 10
    HEARTBEAT_ACK = 11

class GatewayCloseCode(Enum):
    """Discord Gateway Close Codes"""
    UNKNOWN_ERROR = 4000
    UNKNOWN_OPCODE = 4001
    DECODE_ERROR = 4002
    NOT_AUTHENTICATED = 4003
    AUTHENTICATION_FAILED = 4004
    ALREADY_AUTHENTICATED = 4005
    INVALID_SEQ = 4007
    RATE_LIMITED = 4008
    SESSION_TIMED_OUT = 4009
    INVALID_SHARD = 4010
    SHARDING_REQUIRED = 4011
    INVALID_API_VERSION = 4012
    INVALID_INTENTS = 4013
    DISALLOWED_INTENTS = 4014

@dataclass
class Message:
    id: int
    channel_id: int
    guild_id: Optional[int]
    author_id: int
    author_name: str
    content: str
    timestamp: str
    attachments: list[str]


@dataclass
class MessageUpdate:
    id: int
    channel_id: int
    guild_id: Optional[int]
    author_id: Optional[int]
    author_name: Optional[str]
    before: Optional[str]
    after: Optional[str]
    edit_timestamp: str
    attachments: list[str]


@dataclass
class MessageDelete:
    id: int
    channel_id: int
    guild_id: Optional[int]
    author_id: Optional[int]
    author_name: Optional[str]
    content: Optional[str]
    timestamp: Optional[str]
    attachments: list[str]


class ThreadSafeLRUCache:
    """Thread-safe LRU Cache implementation"""
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.cache = OrderedDict()
        self.lock = threading.RLock()
    
    def get(self, key: int) -> Optional[Any]:
        """Get item from cache if exists, marking it as recently used"""
        with self.lock:
            if key not in self.cache:
                return None
            self.cache.move_to_end(key)
            return self.cache[key]
    
    def put(self, key: int, value: Any) -> None:
        """Add item to cache, evicting least recently used if needed"""
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
            self.cache[key] = value
            if len(self.cache) > self.capacity:
                self.cache.popitem(last=False)
    
    def pop(self, key: int) -> Optional[Any]:
        """Remove and return item from cache"""
        with self.lock:
            return self.cache.pop(key, None)
    
    def __contains__(self, key: int) -> bool:
        """Check if key exists in cache"""
        with self.lock:
            return key in self.cache
    
    def __len__(self) -> int:
        """Return number of items in cache"""
        with self.lock:
            return len(self.cache)

class MessageHandler:
    """
    Handles Discord gateway connections and message events.

    Args:
        bot: The bot instance
        on_message: Callback for message creation events
        on_message_update: Callback for message update events
        on_message_delete: Callback for message deletion events
        cache_size: Maximum number of messages to cache (default: 5000)
    """
    
    def __init__(self, bot,
                 on_message: Optional[Callable[[Message], Any]] = None,
                 on_message_update: Optional[Callable[[MessageUpdate], Any]] = None,
                 on_message_delete: Optional[Callable[[MessageDelete], Any]] = None,
                 cache_size: int = 5000):
        self.bot = bot

        self.on_message = on_message
        self.on_message_update = on_message_update
        self.on_message_delete = on_message_delete

        self.cache = ThreadSafeLRUCache(cache_size)
        self.cache_size = cache_size

        self.ws_app: Optional[websocket.WebSocketApp] = None
        self.ws_thread: Optional[threading.Thread] = None
        self.ws_stop_event = threading.Event()
        self.ws_connected = False
        self.sequence: Optional[int] = None
        self.heartbeat_interval: Optional[float] = None
        self.heartbeat_thread: Optional[threading.Thread] = None
        self.last_heartbeat_ack = time.time()
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 10
        self.session_id: Optional[str] = None
        self.fatal_error_occurred = False
        
        self.send_queue = Queue()
        
        self.sequence_lock = threading.RLock()
        self.connection_lock = threading.RLock()

    @staticmethod
    def extract_attachments(d: dict) -> list[str]:
        return [att.get("url") for att in d.get("attachments", []) if att.get("url")]

    def start(self) -> None:
        """Start WebSocket connection in a separate thread"""
        with self.connection_lock:
            if self.ws_thread and self.ws_thread.is_alive():
                logger.warning("WebSocket thread is already running")
                return
            
            self.fatal_error_occurred = False
            self.ws_stop_event.clear()
            self.ws_thread = threading.Thread(
                target=self.run_websocket, 
                daemon=True,
                name="DiscordWebSocketThread"
            )
            self.ws_thread.start()
            logger.info("WebSocket thread started")

    def stop(self) -> None:
        """Stop WebSocket connection and clean up resources"""
        with self.connection_lock:
            self.ws_stop_event.set()
            
            if self.ws_app:
                try:
                    self.ws_app.close()
                except Exception as e:
                    logger.error(f"Error closing WebSocket: {e}")
            
            if self.heartbeat_thread and self.heartbeat_thread.is_alive():
                self.heartbeat_thread.join(timeout=2)
            
            if self.ws_thread and self.ws_thread.is_alive():
                self.ws_thread.join(timeout=3)
            
            logger.info("WebSocket connection stopped")

    def calculate_reconnect_delay(self) -> float:
        """Calculate exponential backoff delay for reconnections"""
        if self.reconnect_attempts == 0:
            return 1.0
        
        delay = min(2 ** self.reconnect_attempts, 30)
        jitter = delay * 0.1
        return delay + (jitter * (2 * (time.time() % 1) - 1))

    def run_websocket(self) -> None:
        """Main WebSocket connection loop with reconnection logic"""
        while not self.ws_stop_event.is_set() and not self.fatal_error_occurred:
            try:
                logger.info("Attempting to connect to Discord Gateway")
                
                self.ws_app = websocket.WebSocketApp(
                    "wss://gateway.discord.gg/?v=9&encoding=json",
                    on_open=self.on_ws_open,
                    on_message=self.on_ws_message,
                    on_error=self.on_ws_error,
                    on_close=self.on_ws_close,
                )
                
                self.ws_app.run_forever(
                    ping_interval=30,
                    ping_timeout=10,
                    reconnect=5
                )
                
            except Exception as e:
                logger.error(f"WebSocket crashed: {e}")
            
            if self.ws_stop_event.is_set() or self.fatal_error_occurred:
                break
                
            if self.reconnect_attempts >= self.max_reconnect_attempts:
                logger.error(f"Maximum reconnection attempts ({self.max_reconnect_attempts}) exceeded. Stopping.")
                break
                
            delay = self.calculate_reconnect_delay()
            logger.info(f"Reconnecting in {delay:.2f} seconds (attempt {self.reconnect_attempts + 1})")
            
            self.reconnect_attempts += 1
            time.sleep(delay)
        
        if self.fatal_error_occurred:
            logger.error("WebSocket connection stopped due to fatal error (invalid token or authentication failed)")
        elif self.ws_stop_event.is_set():
            logger.info("WebSocket connection stopped normally")
        else:
            logger.info("WebSocket connection stopped")

    def on_ws_open(self, ws: websocket.WebSocketApp) -> None:
        """Handle WebSocket connection opening"""
        with self.connection_lock:
            self.ws_connected = True
            self.reconnect_attempts = 0
            logger.info("WebSocket connection established")
            
            if self.session_id and self.sequence:
                payload = self.create_resume_payload()
                logger.info("Attempting to resume session")
            else:
                payload = self.create_identify_payload()
                logger.info("Sending identify payload")
            
            ws.send(json.dumps(payload))

    def create_identify_payload(self) -> Dict:
        """Create identify payload for Discord Gateway"""
        return {
            "op": GatewayOpcode.IDENTIFY.value,
            'd': {
                'token': self.bot.token,
                'properties': {
                    '$os': 'linux',
                    '$browser': 'chrome',
                    '$device': 'chrome'
                }
            }
        }

    def create_resume_payload(self) -> Dict:
        """Create resume payload for Discord Gateway"""
        return {
            "op": GatewayOpcode.RESUME.value,
            "d": {
                "token": self.bot.token,
                "session_id": self.session_id,
                "seq": self.sequence
            }
        }

    def on_ws_message(self, ws: websocket.WebSocketApp, raw: str) -> None:
        """Handle incoming WebSocket messages"""
        try:
            event = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON message: {e}")
            return

        op = event.get("op")
        t = event.get("t")
        d = event.get("d")
        s = event.get("s")

        if s is not None:
            with self.sequence_lock:
                self.sequence = s

        if op == GatewayOpcode.HELLO.value:
            self.handle_hello(ws, d)
        elif op == GatewayOpcode.HEARTBEAT_ACK.value:
            self.handle_heartbeat_ack()
        elif op == GatewayOpcode.RECONNECT.value:
            self.handle_reconnect(ws)
        elif op == GatewayOpcode.INVALID_SESSION.value:
            self.handle_invalid_session(ws, d)
        elif op == GatewayOpcode.DISPATCH.value:
            self.handle_dispatch_event(t, d)

    def handle_hello(self, ws: websocket.WebSocketApp, data: Dict) -> None:
        """Handle HELLO event and start heartbeat"""
        self.heartbeat_interval = data["heartbeat_interval"] / 1000.0
        logger.info(f"Heartbeat interval: {self.heartbeat_interval}s")
        self.start_heartbeat(ws)

    def handle_heartbeat_ack(self) -> None:
        """Handle heartbeat acknowledgment"""
        self.last_heartbeat_ack = time.time()
        logger.debug("Heartbeat ACK received")

    def handle_reconnect(self, ws: websocket.WebSocketApp) -> None:
        """Handle reconnect request from Discord"""
        logger.info("Received reconnect request from Discord")
        ws.close()

    def handle_invalid_session(self, ws: websocket.WebSocketApp, data: Dict) -> None:
        """Handle invalid session event from Discord"""
        resumable = data if isinstance(data, bool) else False
        logger.warning(f"Invalid session received, resumable: {resumable}")
        
        if not resumable:
            self.session_id = None
            with self.sequence_lock:
                self.sequence = None
        
        time.sleep(1)
        ws.close()

    def handle_dispatch_event(self, event_type: str, data: Dict) -> None:
        """Handle dispatch events from Discord"""
        if event_type == "READY":
            self.session_id = data.get("session_id")
            logger.info(f"Ready received, session_id: {self.session_id}")
        
        if event_type == "MESSAGE_CREATE":
            self.handle_message_create(data)
        elif event_type == "MESSAGE_UPDATE":
            self.handle_message_update(data)
        elif event_type == "MESSAGE_DELETE":
            self.handle_message_delete(data)
        elif event_type == "CHANNEL_CREATE":
            self.handle_channel_create(data)

    def handle_message_create(self, data: Dict) -> None:
        """Handle MESSAGE_CREATE event"""
        msg = self.build_message(data)
        if msg:
            self.cache.put(msg.id, msg)
            if self.on_message:
                asyncio.run_coroutine_threadsafe(
                    self.on_message(msg), 
                    self.bot.loop
                )

    def handle_message_update(self, data: Dict) -> None:
        """Handle MESSAGE_UPDATE event"""
        msg = self.build_message_update(data)
        if msg:
            cached_msg = self.cache.get(msg.id)
            if cached_msg:
                msg.before = cached_msg.content
    
                if msg.after:
                    cached_msg.content = msg.after
    
                if getattr(msg, "attachments", None):
                    try:
                        cached_msg.attachments = list(msg.attachments)
                    except Exception:
                        cached_msg.attachments = [
                            a.get("url") if isinstance(a, dict) and "url" in a else str(a)
                            for a in msg.attachments
                        ]
    
                self.cache.put(msg.id, cached_msg)
    
            if self.on_message_update:
                asyncio.run_coroutine_threadsafe(
                    self.on_message_update(msg),
                    self.bot.loop
                )

    def handle_message_delete(self, data: Dict) -> None:
        """Handle MESSAGE_DELETE event"""
        msg = self.build_message_delete(data)
        if msg:
            cached_msg = self.cache.pop(msg.id)
            if cached_msg:
                msg.author_id = cached_msg.author_id
                msg.author_name = cached_msg.author_name
                msg.content = cached_msg.content
                msg.timestamp = cached_msg.timestamp
    
                try:
                    msg.attachments = list(cached_msg.attachments) if getattr(cached_msg, "attachments", None) else []
                except Exception:
                    if getattr(cached_msg, "attachments", None):
                        msg.attachments = [
                            a.get("url") if isinstance(a, dict) and "url" in a else str(a)
                            for a in cached_msg.attachments
                        ]
                    else:
                        msg.attachments = []
    
            if self.on_message_delete:
                asyncio.run_coroutine_threadsafe(
                    self.on_message_delete(msg),
                    self.bot.loop
                )

    def handle_channel_create(self, data: Dict) -> None:
        """Handle CHANNEL_CREATE event (group chat invites)"""
        try:
            if data.get('type') == 3:
                if self.on_message:
                    channel_msg = Message(
                        id=0,
                        channel_id=data['id'],
                        guild_id=None,
                        author_id=0,
                        author_name="System",
                        content="CHANNEL_CREATE",
                        timestamp=time.time(),
                        attachments=[]
                    )
                    asyncio.run_coroutine_threadsafe(
                        self.on_message(channel_msg), 
                        self.bot.loop
                    )
        except Exception as e:
            logger.error(f"Error handling channel create: {e}")

    def start_heartbeat(self, ws: websocket.WebSocketApp) -> None:
        """Start heartbeat thread with ACK verification"""
        def heartbeat_loop():
            logger.info("Heartbeat loop started")
            
            while not self.ws_stop_event.is_set() and self.ws_connected and not self.fatal_error_occurred:
                try:
                    with self.sequence_lock:
                        seq = self.sequence
                    
                    heartbeat_payload = {
                        "op": GatewayOpcode.HEARTBEAT.value,
                        "d": seq
                    }
                    
                    ws.send(json.dumps(heartbeat_payload))
                    logger.debug("Heartbeat sent")
                    
                    time_since_ack = time.time() - self.last_heartbeat_ack
                    if time_since_ack > self.heartbeat_interval * 2:
                        logger.warning(
                            f"No heartbeat ACK received for {time_since_ack:.2f}s, "
                            f"reconnecting"
                        )
                        ws.close()
                        break
                        
                except Exception as e:
                    logger.error(f"Heartbeat failed: {e}")
                    break
                
                time.sleep(self.heartbeat_interval or 20)
            
            logger.info("Heartbeat loop stopped")

        self.heartbeat_thread = threading.Thread(
            target=heartbeat_loop, 
            daemon=True,
            name="DiscordHeartbeatThread"
        )
        self.heartbeat_thread.start()

    def on_ws_error(self, ws: websocket.WebSocketApp, error: Any) -> None:
        """Handle WebSocket errors"""
        logger.error(f"WebSocket error: {error}")

    def on_ws_close(self, ws: websocket.WebSocketApp, code: int, msg: str) -> None:
        """Handle WebSocket connection closing"""
        self.ws_connected = False
        
        try:
            close_code = GatewayCloseCode(code)
            logger.warning(f"WebSocket closed with code {code} ({close_code.name}): {msg}")
            
            if code in [
                GatewayCloseCode.AUTHENTICATION_FAILED.value,
                GatewayCloseCode.INVALID_INTENTS.value,
                GatewayCloseCode.DISALLOWED_INTENTS.value,
                GatewayCloseCode.INVALID_SHARD.value,
                GatewayCloseCode.SHARDING_REQUIRED.value,
                GatewayCloseCode.INVALID_API_VERSION.value,
            ]:
                logger.error(f"Fatal close code {code} received. Stopping reconnection attempts.")
                self.fatal_error_occurred = True
                self.ws_stop_event.set()
                
        except ValueError:
            logger.warning(f"WebSocket closed with unknown code {code}: {msg}")
    
    def build_message(self, d: dict) -> Optional[Message]:
        try:
            author = d.get("author", {})
            return Message(
                id=int(d["id"]),
                channel_id=int(d["channel_id"]),
                guild_id=int(d["guild_id"]) if d.get("guild_id") else None,
                author_id=int(author.get("id", 0)),
                author_name=author.get("username", "Unknown"),
                content=d.get("content", ""),
                timestamp=d.get("timestamp", ""),
                attachments=self.extract_attachments(d),
            )
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Failed to build message: {e}, data: {d}")
            return None
    
    def build_message_update(self, d: dict) -> Optional[MessageUpdate]:
        try:
            author = d.get("author", {})
            return MessageUpdate(
                id=int(d["id"]),
                channel_id=int(d["channel_id"]),
                guild_id=int(d["guild_id"]) if d.get("guild_id") else None,
                author_id=int(author["id"]) if author else None,
                author_name=author.get("username") if author else None,
                before=None,
                after=d.get("content"),
                edit_timestamp=d.get("edited_timestamp", ""),
                attachments=self.extract_attachments(d),
            )
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Failed to build message update: {e}, data: {d}")
            return None
    
    def build_message_delete(self, d: dict) -> Optional[MessageDelete]:
        """Build a MessageDelete object"""
        try:
            return MessageDelete(
                id=int(d["id"]),
                channel_id=int(d["channel_id"]),
                guild_id=int(d["guild_id"]) if d.get("guild_id") else None,
                author_id=None,
                author_name=None,
                content=None,
                timestamp=None,
                attachments=self.extract_attachments(d) or [],
            )
        except (KeyError, ValueError, TypeError) as e:
            logger.error(f"Failed to build message delete: {e}, data: {d}")
            return None