"""IPC Protocol for multi-instance Blender communication.

This module defines the protocol messages used for communication between
the hub instance and secondary instances via Windows named pipes.
"""

import json
from typing import Dict, Any, Optional
from enum import Enum


class MessageType(Enum):
    """IPC message types."""
    REGISTER = "REGISTER"           # Secondary -> Hub: Register new instance
    UNREGISTER = "UNREGISTER"       # Secondary -> Hub: Unregister instance
    CLAIM_ACTIVE = "CLAIM_ACTIVE"   # Secondary -> Hub: Request to become active
    RELEASE_ACTIVE = "RELEASE_ACTIVE"  # Secondary -> Hub: Release active status
    HEARTBEAT = "HEARTBEAT"         # Bidirectional: Keep-alive ping
    IMPORT_DATA = "IMPORT_DATA"     # Hub -> Active: Forward Bridge import data
    ACK = "ACK"                     # Bidirectional: Acknowledge message
    ERROR = "ERROR"                 # Bidirectional: Error response
    QUERY_STATUS = "QUERY_STATUS"   # Secondary -> Hub: Query current status
    STATUS_RESPONSE = "STATUS_RESPONSE"  # Hub -> Secondary: Status information


class IPCMessage:
    """Represents an IPC message."""

    def __init__(self, msg_type: MessageType, data: Optional[Dict[str, Any]] = None):
        """Initialize IPC message.

        Args:
            msg_type: Type of message
            data: Optional message payload
        """
        self.type = msg_type
        self.data = data or {}

    def serialize(self) -> bytes:
        """Serialize message to JSON bytes for transmission.

        Returns:
            bytes: JSON-encoded message
        """
        message_dict = {
            'type': self.type.value,
            'data': self.data
        }

        json_str = json.dumps(message_dict)
        return json_str.encode('utf-8')

    @staticmethod
    def deserialize(data: bytes) -> Optional['IPCMessage']:
        """Deserialize message from JSON bytes.

        Args:
            data: JSON-encoded message bytes

        Returns:
            IPCMessage or None if deserialization fails
        """
        try:
            json_str = data.decode('utf-8')
            message_dict = json.loads(json_str)

            msg_type_str = message_dict.get('type')
            if not msg_type_str:
                return None

            # Convert string to enum
            try:
                msg_type = MessageType(msg_type_str)
            except ValueError:
                print(f"⚠️ Unknown message type: {msg_type_str}")
                return None

            msg_data = message_dict.get('data', {})

            return IPCMessage(msg_type, msg_data)

        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            print(f"❌ Failed to deserialize IPC message: {e}")
            return None

    def __repr__(self) -> str:
        """String representation of message."""
        return f"IPCMessage(type={self.type.value}, data={self.data})"


def create_register_message(pid: int, instance_name: str) -> IPCMessage:
    """Create a REGISTER message.

    Args:
        pid: Process ID of registering instance
        instance_name: Display name of instance

    Returns:
        IPCMessage
    """
    return IPCMessage(MessageType.REGISTER, {
        'pid': pid,
        'name': instance_name
    })


def create_unregister_message(pid: int) -> IPCMessage:
    """Create an UNREGISTER message.

    Args:
        pid: Process ID to unregister

    Returns:
        IPCMessage
    """
    return IPCMessage(MessageType.UNREGISTER, {
        'pid': pid
    })


def create_claim_active_message(pid: int, instance_name: str) -> IPCMessage:
    """Create a CLAIM_ACTIVE message.

    Args:
        pid: Process ID claiming active status
        instance_name: Display name of instance

    Returns:
        IPCMessage
    """
    return IPCMessage(MessageType.CLAIM_ACTIVE, {
        'pid': pid,
        'name': instance_name
    })


def create_release_active_message(pid: int) -> IPCMessage:
    """Create a RELEASE_ACTIVE message.

    Args:
        pid: Process ID releasing active status

    Returns:
        IPCMessage
    """
    return IPCMessage(MessageType.RELEASE_ACTIVE, {
        'pid': pid
    })


def create_heartbeat_message(pid: int) -> IPCMessage:
    """Create a HEARTBEAT message.

    Args:
        pid: Process ID sending heartbeat

    Returns:
        IPCMessage
    """
    return IPCMessage(MessageType.HEARTBEAT, {
        'pid': pid
    })


def create_import_data_message(import_requests: list) -> IPCMessage:
    """Create an IMPORT_DATA message.

    Args:
        import_requests: List of import request dictionaries

    Returns:
        IPCMessage
    """
    return IPCMessage(MessageType.IMPORT_DATA, {
        'import_requests': import_requests
    })


def create_ack_message(original_type: Optional[str] = None) -> IPCMessage:
    """Create an ACK message.

    Args:
        original_type: Optional type of message being acknowledged

    Returns:
        IPCMessage
    """
    data = {}
    if original_type:
        data['ack_for'] = original_type

    return IPCMessage(MessageType.ACK, data)


def create_error_message(error: str, original_type: Optional[str] = None) -> IPCMessage:
    """Create an ERROR message.

    Args:
        error: Error description
        original_type: Optional type of message that caused error

    Returns:
        IPCMessage
    """
    data = {'error': error}
    if original_type:
        data['error_for'] = original_type

    return IPCMessage(MessageType.ERROR, data)


def create_query_status_message(pid: int) -> IPCMessage:
    """Create a QUERY_STATUS message.

    Args:
        pid: Process ID requesting status

    Returns:
        IPCMessage
    """
    return IPCMessage(MessageType.QUERY_STATUS, {
        'pid': pid
    })


def create_status_response_message(active_pid: Optional[int],
                                   active_name: Optional[str],
                                   registered_instances: list) -> IPCMessage:
    """Create a STATUS_RESPONSE message.

    Args:
        active_pid: PID of active instance (or None)
        active_name: Name of active instance (or None)
        registered_instances: List of registered instance info

    Returns:
        IPCMessage
    """
    return IPCMessage(MessageType.STATUS_RESPONSE, {
        'active_instance': {
            'pid': active_pid,
            'name': active_name
        } if active_pid else None,
        'registered_instances': registered_instances
    })
