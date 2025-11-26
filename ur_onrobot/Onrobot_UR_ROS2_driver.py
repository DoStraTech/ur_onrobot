#!/usr/bin/env python3
# Copyright 2025
# SPDX-License-Identifier: MIT
#
# Onrobot_UR_ROS2_driver.py
#
# ROS 2 node wrapping UR_onrobot UniversalGripper.
#
# Topics:
#   ~/status           (std_msgs/String) — JSON snapshot
#   ~/busy             (std_msgs/Bool)
#   ~/object_detected  (std_msgs/Bool)
#   ~/status_code      (std_msgs/Int32)
#   ~/width            (std_msgs/Float32)   # FG/RG
#   ~/vacuum           (std_msgs/String)    # VG, JSON {"A":..,"B":..} or raw struct
#
# Action:
#   ~/gripper_command  (control_msgs/action/GripperCommand)
#     FG/RG: command.position=width_mm, command.max_effort=force, speed param
#     VG:    command.position=vacuum_percent (0..100) applied to both by default
#
# Params:
#   ip (string, required)
#   gid (int, default auto 0..3)
#   status_hz (double, default 5.0)
#   action.timeout_s (double, default 5.0)
#   action.feedback_hz (double, default 10.0)
#   fg.default_speed (int 1..100, default 50)
#   vg.apply_both (bool, default True)
#   vg.threshold_gripped (double, default 20.0)

import json, time, rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from std_msgs.msg import String, Bool, Int32, Float32
from control_msgs.action import GripperCommand
from .UR_onrobot import make_universal, snapshot
from nit_utils.helpers import unique_node

class GripperNode(Node):
    def __init__(self):
        super().__init__("ur_onrobot")
        unique_node(self)
        self.declare_parameter("ip", "")
        self.declare_parameter("gid", -1)
        self.declare_parameter("status_hz", 5.0)
        self.declare_parameter("action.timeout_s", 5.0)
        self.declare_parameter("action.feedback_hz", 10.0)
        self.declare_parameter("fg.default_speed", 50)
        self.declare_parameter("vg.apply_both", True)
        self.declare_parameter("vg.threshold_gripped", 20.0)
        self.declare_parameter("safety.enforce", True)       
        self.declare_parameter("safety.latched_abort", True) 


        ip = self.get_parameter("ip").get_parameter_value().string_value
        gid = self.get_parameter("gid").get_parameter_value().integer_value
        if not ip:
            raise RuntimeError("param 'ip' is required")

        gids = range(gid, gid + 1) if gid >= 0 else range(0, 4)
        self.g = make_universal(ip, gids)
        self.get_logger().info(f"Connected: {snapshot(self.g)}")

        self.pub_status = self.create_publisher(String, "~/status", 10)
        self.pub_busy   = self.create_publisher(Bool,   "~/busy", 10)
        self.pub_obj    = self.create_publisher(Bool,   "~/object_detected", 10)
        self.pub_code   = self.create_publisher(Int32,  "~/status_code", 10)
        self.pub_width  = self.create_publisher(Float32,"~/width", 10)  if self.g.family in ("FG","RG") else None
        self.pub_vac    = self.create_publisher(String, "~/vacuum", 10) if self.g.family == "VG" else None

        # # Safety topics (always exist; publish False on non-RG)
        # self.pub_safe_ok   = self.create_publisher(Bool,   "safety_ok",     10)
        # self.pub_s1_pushed = self.create_publisher(Bool,   "s1_pushed",     10)
        # self.pub_s1_trig   = self.create_publisher(Bool,   "s1_triggered",  10)
        # self.pub_s2_pushed = self.create_publisher(Bool,   "s2_pushed",     10)
        # self.pub_s2_trig   = self.create_publisher(Bool,   "s2_triggered",  10)
        # self.pub_safe_fail = self.create_publisher(Bool,   "safety_failed", 10)


        hz = float(self.get_parameter("status_hz").value)
        self.timer = self.create_timer(1.0 / max(0.1, hz), self._tick_status)

        self.fb_dt  = 1.0 / max(1e-3, float(self.get_parameter("action.feedback_hz").value))
        self.timeout= float(self.get_parameter("action.timeout_s").value)
        self.speed_default = int(self.get_parameter("fg.default_speed").value)
        self.vg_both = bool(self.get_parameter("vg.apply_both").value)
        self.vg_thr  = float(self.get_parameter("vg.threshold_gripped").value)

        self.action = ActionServer(
            self, GripperCommand, "gripper_command",
            execute_callback=self._execute_cb,
            cancel_callback=lambda gh: CancelResponse.ACCEPT,
            goal_callback=lambda gr: GoalResponse.ACCEPT
        )

    def _tick_status(self):
        try:
            fam = self.g.family
            busy = bool(self.g.is_busy())
            obj  = bool(self.g.object_detected())
            code = int(self.g.status())
            msg = {"family": fam, "ns": self.g.ns, "gid": self.g.gid, "busy": busy, "object": obj, "status": code, "limits": self.g.limits()}
            if fam == "VG":
                vac = self.g.get_vacuum()
                msg["vacuum"] = vac
                if self.pub_vac:
                    self.pub_vac.publish(String(data=json.dumps(vac if vac is not None else {})))
            else:
                w = float(self.g.get_width())
                msg["width"] = w
                if self.pub_width:
                    self.pub_width.publish(Float32(data=w))
            self.pub_status.publish(String(data=json.dumps(msg)))
            self.pub_busy.publish(Bool(data=busy))
            self.pub_obj.publish(Bool(data=obj))
            self.pub_code.publish(Int32(data=code))
        except Exception as e:
            self.get_logger().warn(f"status tick error: {e}")

    def _execute_cb(self, goal_handle):
        goal: GripperCommand.Goal = goal_handle.request
        fam = self.g.family
        start = time.time()

        try:
            if fam == "VG":
                pct = int(max(0, min(100, int(goal.command.position))))
                if self.vg_both:
                    self.g.set_vacuum(pct, pct)
                else:
                    self.g.set_vacuum(pct, None)
            else:
                force = float(goal.command.max_effort) if goal.command.max_effort == goal.command.max_effort else 30.0
                speed = self.speed_default if fam == "FG" else 50
                self.g.set_width_force(float(goal.command.position), force, int(speed))
        except Exception as e:
            self.get_logger().error(f"command error: {e}")
            res = GripperCommand.Result()
            res.position = float("nan"); res.effort = float("nan"); res.stalled = True; res.reached_goal = False
            goal_handle.abort()
            return res

        last_fb = 0.0
        while rclpy.ok():
            if goal_handle.is_cancel_requested:
                goal_handle.canceled()
                return GripperCommand.Result()

            now = time.time()
            busy = self.g.is_busy()
            obj  = self.g.object_detected()

            if fam == "VG":
                vac = self.g.get_vacuum() or {}
                cur = float(max(vac.get("A", 0), vac.get("B", 0))) if isinstance(vac, dict) else 0.0
                target = int(max(0, min(100, int(goal.command.position))))
                reached = (cur >= target - 1.0) or (obj and cur >= self.vg_thr)
                fb = GripperCommand.Feedback(position=cur, effort=0.0, stalled=(not busy and not reached), reached_goal=reached)
            else:
                w = self.g.get_width()
                cur = float(w) if w == w else float("nan")
                tol = 1.0
                reached = (cur == cur) and (abs(cur - float(goal.command.position)) <= tol or obj)
                eff = float(goal.command.max_effort) if goal.command.max_effort == goal.command.max_effort else 0.0
                fb = GripperCommand.Feedback(position=cur, effort=eff, stalled=(not busy and not reached), reached_goal=reached)

            if (now - last_fb) >= self.fb_dt:
                goal_handle.publish_feedback(fb)
                last_fb = now

            if not busy and fb.reached_goal:
                res = GripperCommand.Result(position=fb.position, effort=fb.effort, stalled=False, reached_goal=True)
                goal_handle.succeed()
                return res

            if (now - start) > self.timeout:
                res = GripperCommand.Result(position=fb.position, effort=fb.effort, stalled=True, reached_goal=False)
                goal_handle.abort()
                return res

            time.sleep(0.02)

def main():
    rclpy.init()
    node = GripperNode()
    try:
        exec = MultiThreadedExecutor(num_threads=2)
        exec.add_node(node)
        exec.spin()
    except KeyboardInterrupt: pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()

if __name__ == "__main__":
    main()
