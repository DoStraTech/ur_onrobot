# ur_onrobot

**ROS 2 driver and URDF/xacro description for Universal Robots with OnRobot grippers**

This package provides:
- XML-RPC helper for OnRobot URCap communication
- ROS 2 action server for gripper control
- URDF/xacro robot description with gripper visualization
- Simulation support with fake hardware
- Integration with UR robots (tested on UR5e, UR10e)

## Features

- **OnRobot 2FG14 Gripper Support**: Full integration with OnRobot's 2-finger gripper
- **Action Server**: ROS 2 action interface for gripper commands
- **URDF Description**: Complete robot + gripper visualization for RViz
- **Simulation Mode**: Use fake hardware for testing without physical robot
- **Camera Mount**: Example camera link included in xacro

## Installation & Build

### Dependencies

```bash
sudo apt-get install ros-humble-ur-description
pip install pycurl
```

### Build

```bash
cd ~/ros2_ws
colcon build --packages-select ur_onrobot
source install/setup.bash
```

## Usage

### Launch Gripper Driver

```bash
# Edit launch file to set your robot's IP address
ros2 launch ur_onrobot ur_onrobot.launch.py
```

**Important**: Update the `ip` parameter in `launch/ur_onrobot.launch.py` to match your robot's IP address.

### Use URDF in Your Launch File

```python
from launch import LaunchDescription
from launch.substitutions import Command, FindExecutable, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare

def generate_launch_description():
    robot_description_content = Command([
        PathJoinSubstitution([FindExecutable(name="xacro")]),
        " ",
        PathJoinSubstitution([
            FindPackageShare("ur_onrobot"),
            "urdf",
            "ur_with_onrobot.xacro"
        ]),
        " robot_ip:=192.168.X.X",  # Your robot IP
        " tf_prefix:=robot_",
    ])
    
    # ... rest of your launch file
```

### Control Gripper via Action

```bash
# Open gripper
ros2 action send_goal /test_gripper/gripper_action control_msgs/action/GripperCommand "{command: {position: 0.055, max_effort: 100.0}}"

# Close gripper
ros2 action send_goal /test_gripper/gripper_action control_msgs/action/GripperCommand "{command: {position: 0.0, max_effort: 100.0}}"
```

## Configuration

### Launch Parameters

Edit `launch/ur_onrobot.launch.py`:

- `ip`: Gripper IP address (typically same as robot IP)
- `namespace`: Robot namespace (e.g., `rondor`, `rosa`)
- `status_hz`: Status update frequency
- `fg.default_speed`: Default gripper speed (0-100)
- `action.timeout_s`: Action timeout in seconds

### URDF/Xacro Arguments

When using `urdf/ur_with_onrobot.xacro`:

- `robot_ip`: Robot IP address (default: `192.168.178.5`)
- `ur_type`: UR model (e.g., `ur5e`, `ur10e`)
- `tf_prefix`: TF prefix for robot links
- `gripper_prefix`: Prefix for gripper links (default: `gripper_`)
- `use_fake_hardware`: Enable simulation mode (default: `false`)

## Package Contents

- `ur_onrobot/`: Python ROS 2 node for gripper control
- `urdf/`: Robot + gripper URDF/xacro descriptions
  - `ur_with_onrobot.xacro`: Complete UR + OnRobot description
  - `onrobot_2fg14.xacro`: Gripper-only description
- `launch/`: Launch files
- `meshes/`: STL files for visualization
- `config/`: Controller configurations

## Tested Hardware

- Universal Robots UR5e
- Universal Robots UR10e  
- OnRobot 2FG14 gripper
- OnRobot RG6 gripper (driver compatible, STL meshes not yet included)

## TODO

- [ ] Add RG6 gripper visualization meshes from [UOsaka-Harada-Laboratory/onrobot](https://github.com/UOsaka-Harada-Laboratory/onrobot/tree/main/onrobot_rg_description/meshes/rg6) (MIT License)
- [ ] Create onrobot_rg6.xacro description file

## Credits

- **STL Meshes**: The 2FG gripper visualization meshes were adapted from [juandpenan/onrobot_2FG7_gripper_description](https://github.com/juandpenan/onrobot_2FG7_gripper_description) (MIT License), originally generated from OnRobot official CAD files using the [fusion2urdf](https://github.com/syuntoku14/fusion2urdf) tool
- **Driver Development**: Neuro Information Technology Lab, Otto von Guericke University Magdeburg

## License

MIT

## Maintainer

**Dominykas Strazdas**  
[DoStraTech](https://github.com/DoStraTech)

Used at the [Neuro Information Technology (NIT) Lab](https://www.nit.ovgu.de), Otto von Guericke University Magdeburg.
