from setuptools import setup, find_packages
from glob import glob
import os

package_name = "ur_onrobot"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/launch", glob("launch/*.launch.py")),
        ("share/" + package_name + "/urdf", glob("urdf/*.xacro")),
        ("share/" + package_name + "/srdf", glob("srdf/*.srdf.xacro")),
        ("share/" + package_name + "/meshes", glob("meshes/*.stl")),
        ("share/" + package_name + "/rviz", glob("rviz/*.rviz")),
        ("share/" + package_name + "/config/ur10e", glob("config/ur10e/*")),
        ("share/" + package_name + "/config/ur5e", glob("config/ur5e/*")),
    ],
    install_requires=[
        "setuptools",
        "pycurl",
    ],


    zip_safe=True,
    maintainer="Dominykas Strazdas",
    maintainer_email="dominykas.strazdas@ovgu.de",
    description="OnRobot URCap XML-RPC helper & ROS 2 driver for Universal Robots",
    license="MIT",
    entry_points={
        "console_scripts": [
            "onrobot-cli = ur_onrobot.UR_onrobot:main",
            "onrobot-ros2 = ur_onrobot.Onrobot_UR_ROS2_driver:main",
            "gripper-joint-state-publisher = ur_onrobot.gripper_joint_state_publisher:main",
            "gripper-simulator = ur_onrobot.gripper_simulator:main",
        ],
    },
)
