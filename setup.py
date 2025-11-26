from setuptools import setup, find_packages

package_name = "ur_onrobot"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/launch", ["launch/ur_onrobot.launch.py"]),
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
        ],
    },
)
