#!/usr/bin/env python3
"""
Simple gripper simulator for OnRobot 2FG14 in simulation mode.

This node simulates the gripper hardware interface by:
- Providing the same topics as the real gripper driver
- Publishing joint states based on commanded positions
- Simulating gripper actions (open/close)
- Providing preset services for testing

This allows the full ROS stack to work identically in both real and sim modes.
"""

import rclpy
from rclpy.node import Node
from rclpy.action import ActionServer, GoalResponse, CancelResponse
from rclpy.qos import QoSProfile, QoSDurabilityPolicy, QoSReliabilityPolicy
from std_msgs.msg import String, Bool, Int32, Float32
from std_srvs.srv import SetBool, Trigger
from control_msgs.action import GripperCommand
from sensor_msgs.msg import JointState
import json
import time


class GripperSimulator(Node):
    """Simulates OnRobot 2FG14 gripper for testing in simulation."""

    def __init__(self):
        super().__init__("gripper")
        
        # Declare parameters matching the real driver
        self.declare_parameter("gripper_prefix", "gripper_")
        self.declare_parameter("publish_rate", 20.0)
        self.declare_parameter("preset.open_width", 55.0)  # FG14 actual range: 5-115mm (inward config)
        self.declare_parameter("preset.close_width", 5.0)
        self.declare_parameter("preset.default_force", 30.0)
        # Simulated jaw travel speed [mm/s] and the bounded action
        # deadline [s].  40.0 mm/s (~1.0 s per 40 mm stroke) keeps the
        # simulated work visible on owner-timelines; the real driver's
        # action contract is unchanged (result on physical reach).
        # 2026-10-09 operator: "make the sim movement time a bit slower".
        self.declare_parameter("sim.speed_mm_s", 40.0)
        self.declare_parameter("sim.timeout_s", 10.0)

        # Get parameters
        self.gripper_prefix = self.get_parameter("gripper_prefix").value
        self.publish_rate = self.get_parameter("publish_rate").value
        self.open_width = self.get_parameter("preset.open_width").value
        self.close_width = self.get_parameter("preset.close_width").value
        self.sim_speed_mm_s = self.get_parameter("sim.speed_mm_s").value
        self.sim_timeout_s = self.get_parameter("sim.timeout_s").value
        
        # State variables
        self.current_width_mm = self.open_width  # Start open
        self.target_width_mm = self.current_width_mm
        self.is_busy = False
        self.object_detected = False
        self.preset_state = "open"  # "open" or "close"
        
        # Joint names (matching URDF)
        self.left_joint_name = f"{self.gripper_prefix}left_finger_joint"
        self.right_joint_name = f"{self.gripper_prefix}right_finger_joint"
        
        # Publishers - matching real driver topics
        self.pub_status = self.create_publisher(String, "~/status", 10)
        self.pub_busy = self.create_publisher(Bool, "~/busy", 10)
        self.pub_object = self.create_publisher(Bool, "~/object_detected", 10)
        self.pub_code = self.create_publisher(Int32, "~/status_code", 10)
        self.pub_width = self.create_publisher(Float32, "~/width", 10)
        
        # Joint state publisher with QoS matching joint_state_broadcaster
        qos_profile = QoSProfile(depth=10, durability=QoSDurabilityPolicy.VOLATILE, reliability=QoSReliabilityPolicy.RELIABLE)
        self.joint_state_pub = self.create_publisher(JointState,"joint_states",qos_profile)
        
        # Action server for gripper commands
        self.action_server = ActionServer(
            self,
            GripperCommand,
            "gripper_command",
            execute_callback=self._execute_gripper_command,
            goal_callback=lambda gr: GoalResponse.ACCEPT,
            cancel_callback=lambda gh: CancelResponse.ACCEPT
        )
        
        # Preset services
        self.srv_toggle = self.create_service(Trigger, "~/preset/toggle", self._preset_toggle_cb)
        self.srv_set_state = self.create_service(SetBool, "~/preset/set_state", self._preset_set_state_cb)
        
        # Timers
        self.status_timer = self.create_timer(0.2, self._publish_status)  # 5 Hz
        self.joint_state_timer = self.create_timer(1.0 / self.publish_rate, self._publish_joint_states)
                
        # Simulation update timer (smooth motion)
        self.sim_timer = self.create_timer(0.02, self._update_simulation)  # 50 Hz
        
        self.get_logger().info("Gripper simulator started")
        self.get_logger().info(f"  - Gripper prefix: {self.gripper_prefix}")
        self.get_logger().info(f"  - Joint names: {self.left_joint_name}, {self.right_joint_name}")
        self.get_logger().info(f"  - Initial width: {self.current_width_mm:.1f} mm")

    def _update_simulation(self):
        """Update gripper position smoothly towards target."""
        if self.current_width_mm != self.target_width_mm:
            speed = float(self.sim_speed_mm_s)  # mm/s (sim.speed_mm_s)
            dt = 0.02  # 50 Hz
            max_delta = speed * dt
            
            delta = self.target_width_mm - self.current_width_mm
            if abs(delta) <= max_delta:
                self.current_width_mm = self.target_width_mm
                self.is_busy = False
            else:
                self.current_width_mm += max_delta if delta > 0 else -max_delta
                self.is_busy = True
                
            # Simulate object detection (detect object if closing and width > 5mm)
            if not self.is_busy and self.current_width_mm < 10.0:
                self.object_detected = True
            else:
                self.object_detected = False

    def _publish_status(self):
        """Publish gripper status topics."""
        status_msg = {
            "family": "FG",
            "ns": "sim",
            "gid": 0,
            "busy": self.is_busy,
            "object": self.object_detected,
            "status": 1 if not self.is_busy else 0,
            "width": self.current_width_mm,
            "limits": {"min": 5.0, "max": 115.0}
        }
        
        self.pub_status.publish(String(data=json.dumps(status_msg)))
        self.pub_busy.publish(Bool(data=self.is_busy))
        self.pub_object.publish(Bool(data=self.object_detected))
        self.pub_code.publish(Int32(data=1 if not self.is_busy else 0))
        self.pub_width.publish(Float32(data=self.current_width_mm))

    def _publish_joint_states(self):
        """Publish joint states for visualization in RViz."""
        joint_position = self.current_width_mm / 2000.0        
        joint_position = max(0.0, min(0.050, joint_position))
        
        msg = JointState()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.name = [self.left_joint_name, self.right_joint_name]
        msg.position = [joint_position, joint_position]
        msg.velocity = [0.0, 0.0]
        msg.effort = [0.0, 0.0]
        
        self.joint_state_pub.publish(msg)

    def _execute_gripper_command(self, goal_handle):
        """Execute gripper command action.

        Honors the REAL OnRobot driver's action contract
        (Onrobot_UR_ROS2_driver._execute_cb): the terminal result is
        returned only once the jaws have PHYSICALLY reached the target
        (busy cleared, same 1.0 mm tolerance), cancel is honored, and
        the wait is bounded (sim.timeout_s -> abort, stalled=True,
        reached_goal=False).

        The old callback returned success immediately
        (``reached_goal=True``) while the background motion was still
        running — divergent from real hardware and invisible on
        owner-timelines (gripper bars were ~40 ms handshakes).  2026-10-09
        fix (operator: sim must behave like the real driver, and the
        movement time must be visible in the E6 plot).
        """
        goal = goal_handle.request
        # Clamp to hardware limits (5-115mm)
        target = max(5.0, min(115.0, goal.command.position))  # Position is width in mm

        self.get_logger().info(f"Gripper command received: {target:.1f} mm")

        if abs(self.current_width_mm - target) <= 1.0:
            # Already at the target: zero work, succeed immediately
            # (otherwise is_busy would stay set and the loop would time out).
            res = GripperCommand.Result()
            res.position = self.current_width_mm
            res.effort = 0.0
            res.stalled = False
            res.reached_goal = True
            goal_handle.succeed()
            return res

        self.target_width_mm = target
        self.is_busy = True

        start = time.monotonic()
        while rclpy.ok():
            if goal_handle.is_cancel_requested:
                goal_handle.canceled()
                return GripperCommand.Result()

            cur = self.current_width_mm
            reached = abs(cur - target) <= 1.0  # same tolerance as the real driver
            if not self.is_busy and reached:
                res = GripperCommand.Result()
                res.position = cur  # actual width in mm, like the real driver
                res.effort = 0.0
                res.stalled = False
                res.reached_goal = True
                goal_handle.succeed()
                return res

            if time.monotonic() - start > self.sim_timeout_s:
                res = GripperCommand.Result()
                res.position = cur
                res.effort = 0.0
                res.stalled = True
                res.reached_goal = False
                goal_handle.abort()
                return res

            time.sleep(0.02)

    def _preset_toggle_cb(self, request, response):
        """Toggle between open and close presets."""
        if self.preset_state == "open":
            self.target_width_mm = self.close_width
            self.preset_state = "close"
            msg = "Closing gripper"
        else:
            self.target_width_mm = self.open_width
            self.preset_state = "open"
            msg = "Opening gripper"
        
        self.is_busy = True
        response.success = True
        response.message = msg
        self.get_logger().info(msg)
        return response

    def _preset_set_state_cb(self, request, response):
        """Set gripper to open (True) or close (False) preset."""
        if request.data:
            self.target_width_mm = self.open_width
            self.preset_state = "open"
            msg = "Opening gripper"
        else:
            self.target_width_mm = self.close_width
            self.preset_state = "close"
            msg = "Closing gripper"
        
        self.is_busy = True
        response.success = True
        response.message = msg
        self.get_logger().info(msg)
        return response


def main(args=None):
    rclpy.init(args=args)
    node = GripperSimulator()
    # Multi-threaded executor: the action execute callback blocks while
    # polling for physical reach (like the real driver polls the hardware
    # thread), so the 50 Hz jaw-movement timer must run in a separate
    # thread.  Single-threaded rclpy.spin() would starve the timer and
    # every real stroke would time out (2026-10-09 fix).
    from rclpy.executors import MultiThreadedExecutor
    ext = MultiThreadedExecutor()
    ext.add_node(node)
    ext.spin()
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
