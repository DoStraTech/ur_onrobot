#!/usr/bin/env python3
"""
Gripper Joint State Publisher for OnRobot 2FG14.

Subscribes to /gripper/width topic (gripper width in mm) and publishes
corresponding joint states for visualization in RViz.
"""

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, QoSDurabilityPolicy, QoSReliabilityPolicy
from std_msgs.msg import Float32
from sensor_msgs.msg import JointState


class GripperJointStatePublisher(Node):
    """Publish joint states for OnRobot gripper based on width feedback."""

    def __init__(self):
        super().__init__("gripper_joint_state_publisher")

        # Declare parameters
        self.declare_parameter("gripper_prefix", "")
        self.declare_parameter("publish_rate", 20.0)  # Hz
        self.declare_parameter("width_topic", "gripper/width")
        
        # Get parameters
        self.gripper_prefix = self.get_parameter("gripper_prefix").value
        publish_rate = self.get_parameter("publish_rate").value
        width_topic = self.get_parameter("width_topic").value

        # Joint names (matching URDF)
        self.left_joint_name = f"{self.gripper_prefix}left_finger_joint"
        self.right_joint_name = f"{self.gripper_prefix}right_finger_joint"

        # Current gripper width in mm
        self.current_width_mm = 0.0
        self.width_received = False

        # Subscribe to gripper width topic
        self.width_sub = self.create_subscription(
            Float32,
            width_topic,
            self.width_callback,
            10
        )

        # Publisher for joint states with QoS matching joint_state_broadcaster
        # Use RELIABLE (works with both RELIABLE and BEST_EFFORT subscribers)
        # Use VOLATILE (most subscribers expect this, not TRANSIENT_LOCAL)
        qos_profile = QoSProfile(
            depth=10,
            durability=QoSDurabilityPolicy.VOLATILE,
            reliability=QoSReliabilityPolicy.RELIABLE
        )
        self.joint_state_pub = self.create_publisher(
            JointState,
            "joint_states",
            qos_profile
        )

        # Publish initial state immediately so MoveIt knows these joints exist
        # Set flag to true so initial publish works
        self.width_received = True
        self.publish_joint_states()

        # Timer for publishing joint states at fixed rate
        self.timer = self.create_timer(
            1.0 / publish_rate,
            self.publish_joint_states
        )

        self.get_logger().info(f"Gripper joint state publisher started")
        self.get_logger().info(f"  - Width topic: {width_topic}")
        self.get_logger().info(f"  - Publish rate: {publish_rate} Hz")
        self.get_logger().info(f"  - Joint names: {self.left_joint_name}, {self.right_joint_name}")

    def width_callback(self, msg: Float32):
        """Update current gripper width from topic."""
        self.current_width_mm = msg.data
        if not self.width_received:
            self.get_logger().info(f"First width received: {self.current_width_mm:.2f} mm")
            self.width_received = True

    def width_to_joint_position(self, width_mm: float) -> float:
        """
        Convert gripper width (mm) to joint position (meters).
        
        FG14 has 140mm total stroke (0-140mm).
        Each finger moves 70mm from center (0-0.070m).
        
        Width = 2 * left_finger_position (both fingers move symmetrically)
        left_finger_position = width / 2000.0  (mm to m, divided by 2)
        
        Args:
            width_mm: Total gripper width in millimeters
            
        Returns:
            Joint position for left_finger_joint in meters
        """
        # Convert total width to per-finger position
        # Width is the gap between fingers, each finger moves half that distance
        joint_position = width_mm / 2000.0  # mm to meters, divide by 2 for per-finger
        
        # Clamp to joint limits (0.0 to 0.070m)
        joint_position = max(0.0, min(0.070, joint_position))
        
        return joint_position

    def publish_joint_states(self):
        """Publish current gripper joint states."""
        if not self.width_received:
            # Don't publish until we have at least one width reading
            return

        # Calculate joint position
        left_position = self.width_to_joint_position(self.current_width_mm)
        
        # Right finger mirrors left finger (mimic joint in URDF handles this,
        # but we publish both for completeness)
        right_position = left_position

        # Create joint state message
        joint_state = JointState()
        joint_state.header.stamp = self.get_clock().now().to_msg()
        joint_state.name = [self.left_joint_name, self.right_joint_name]
        joint_state.position = [left_position, right_position]
        joint_state.velocity = []
        joint_state.effort = []

        # Publish
        self.joint_state_pub.publish(joint_state)


def main(args=None):
    rclpy.init(args=args)
    node = GripperJointStatePublisher()
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
