#!/usr/bin/env python3
from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    return LaunchDescription([
        Node(
            package="ur_onrobot",
            executable="onrobot-ros2",
            name="ur_onrobot",
            output="screen",
            parameters=[{
                "ip": "192.168.178.5",     # CHANGE THIS: Set to your robot's IP address
                "status_hz": 5.0,
                "fg.default_speed": 50,
                "vg.apply_both": True,
                "vg.threshold_gripped": 20.0,
                "action.timeout_s": 5.0,
                "action.feedback_hz": 10.0,
            }],
            namespace="robot",  # CHANGE THIS: Set to your robot's namespace (e.g., rondor, rosa)
        )
    ])
