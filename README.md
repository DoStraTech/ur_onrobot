# ur_onrobot

**ROS 2 driver and URDF/xacro description for Universal Robots with OnRobot grippers**

This package communicates directly with the **OnRobot URCap** installed on the UR controller via **XML-RPC** (port 41414). Because it talks to the URCap independently of the UR robot program, the gripper can be commanded **while the robot is in motion** — enabling use cases like throwing and catching objects, or adjusting grip during trajectories.

On startup, the driver **automatically scans the XML-RPC interface** to discover which gripper is connected and what methods are available. This means it works with any OnRobot gripper that exposes the standard URCap API, even models not explicitly tested here.

## Supported Grippers

| Family | Models | Tested | Notes |
|--------|--------|--------|-------|
| **FG** (Finger Gripper) | 2FG7, 2FG14 | 2FG14 ✓ | Width + force + speed control |
| **RG** (Robot Gripper) | RG2, RG6 | RG6 ✓ | Width + force control, safety buttons |
| **VG** (Vacuum Gripper) | VG10, VGC10, VGP30 | — | Vacuum A/B channel control |

The driver should work with **any OnRobot gripper** connected via the URCap Compute Box or Tool I/O, as it discovers available methods dynamically via `system.listMethods`.

## Features

- **UR-Independent Communication**: Talks directly to URCap XML-RPC, not through the UR program — gripper moves while robot moves
- **Auto-Discovery**: Scans XML-RPC API to detect gripper family (FG/RG/VG), model, and capabilities
- **Action Server**: Standard `control_msgs/action/GripperCommand` interface
- **Preset Services**: Quick open/close via `std_srvs/Trigger` and `std_srvs/SetBool`
- **Status Publishing**: Continuous width, busy, object detection, and status topics
- **URDF Description**: Complete robot + gripper visualization for RViz
- **Simulation Mode**: Fake hardware for testing without physical robot
- **CLI Tool**: Standalone command-line introspection and control (no ROS needed)

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
ros2 launch ur_onrobot ur_onrobot.launch.py
```

> **Important**: Edit `launch/ur_onrobot.launch.py` and set the `ip` parameter to your robot's IP address.

### Recommended: Launch via Robot Config YAML

In production, the driver is typically launched as part of a larger robot stack with parameters from a YAML config file:

```python
Node(
    package="ur_onrobot",
    executable="onrobot-ros2",
    name="gripper",
    output="screen",
    parameters=[robot_config],  # YAML file with ip, speeds, presets, etc.
)
```

Example YAML (`robot_config.yaml`):
```yaml
gripper:
  ros__parameters:
    ip: "192.168.178.5"
    status_hz: 5.0
    fg.default_speed: 50
    action.timeout_s: 5.0
    action.feedback_hz: 10.0
    preset.open_width: 55.0
    preset.close_width: 5.0
    preset.default_force: 30.0
```

### Control Gripper via Action

The action server is at `~/gripper_command` (under the node's namespace):

```bash
# Open gripper (FG/RG: position=width in mm, max_effort=force)
ros2 action send_goal /gripper_command \
  control_msgs/action/GripperCommand \
  "{command: {position: 55.0, max_effort: 30.0}}"
```

Example output:
```
Waiting for an action server to become available...
Sending goal:
     command:
  position: 55.0
  max_effort: 30.0

Goal accepted with ID: 2633e5c9f62448af8d7f2bf32bb36679

Result:
    position: 54.60000228881836
  effort: 30.0
  stalled: false
  reached_goal: true
```

```bash
# Close gripper
ros2 action send_goal /gripper_command \
  control_msgs/action/GripperCommand \
  "{command: {position: 0.0, max_effort: 30.0}}"
```

> If using a namespace, prefix accordingly (e.g., `/rondor/gripper/gripper_command`).

### Preset Services (FG/RG only)

```bash
# Toggle between open and close
ros2 service call /gripper/preset/toggle std_srvs/srv/Trigger
```

Example — toggling twice:
```
requester: making request: std_srvs.srv.Trigger_Request()
response:
std_srvs.srv.Trigger_Response(success=True, message='Preset: open (width=55.0mm)')

requester: making request: std_srvs.srv.Trigger_Request()
response:
std_srvs.srv.Trigger_Response(success=True, message='Preset: close (width=5.0mm)')
```

```bash
# Explicit open (True) or close (False)
ros2 service call /gripper/preset/set_state std_srvs/srv/SetBool "{data: true}"
```

### CLI Tool (No ROS Required)

Introspect the XML-RPC API and control the gripper directly:

```bash
# Dump all available methods to JSON and Markdown
onrobot-cli 192.168.178.5

# Move gripper (FG/RG)
onrobot-cli 192.168.178.5 --move --width 30 --force 20 --speed 50
```

## ROS 2 Interface

### Published Topics

| Topic | Type | Description |
|-------|------|-------------|
| `~/status` | `std_msgs/String` | JSON snapshot (family, width/vacuum, busy, object, status) |
| `~/busy` | `std_msgs/Bool` | Gripper is currently moving |
| `~/object_detected` | `std_msgs/Bool` | Grip/object detection |
| `~/status_code` | `std_msgs/Int32` | Gripper status code |
| `~/width` | `std_msgs/Float32` | Current width in mm (FG/RG only) |
| `~/vacuum` | `std_msgs/String` | Vacuum state as JSON (VG only) |

### Action Server

| Action | Type | Description |
|--------|------|-------------|
| `~/gripper_command` | `control_msgs/action/GripperCommand` | FG/RG: position=width_mm, max_effort=force. VG: position=vacuum_percent |

### Services (FG/RG only)

| Service | Type | Description |
|---------|------|-------------|
| `~/preset/toggle` | `std_srvs/Trigger` | Toggle between open/close presets |
| `~/preset/set_state` | `std_srvs/SetBool` | True=open, False=close |

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `ip` | string | *required* | Robot/gripper IP address |
| `gid` | int | -1 (auto) | Gripper ID (auto-scans 0-3) |
| `status_hz` | double | 5.0 | Status publishing rate |
| `action.timeout_s` | double | 5.0 | Action timeout |
| `action.feedback_hz` | double | 10.0 | Action feedback rate |
| `fg.default_speed` | int | 50 | FG gripper speed (1-100) |
| `vg.apply_both` | bool | true | Apply vacuum to both channels |
| `vg.threshold_gripped` | double | 20.0 | VG grip detection threshold |
| `preset.open_width` | double | 60.0 | Open preset width (mm) |
| `preset.close_width` | double | 0.0 | Close preset width (mm) |
| `preset.default_force` | double | 30.0 | Preset force |

### Executables

| Entry Point | Description |
|-------------|-------------|
| `onrobot-ros2` | Main ROS 2 driver node |
| `onrobot-cli` | Standalone CLI tool (no ROS) |
| `gripper-joint-state-publisher` | Converts width to joint states for URDF visualization |
| `gripper-simulator` | Simulates gripper for testing without hardware |

## URDF/Xacro

### Use in Your Launch File

```python
from launch.substitutions import Command, FindExecutable, PathJoinSubstitution
from launch_ros.substitutions import FindPackageShare

robot_description_content = Command([
    PathJoinSubstitution([FindExecutable(name="xacro")]),
    " ",
    PathJoinSubstitution([
        FindPackageShare("ur_onrobot"),
        "urdf", "ur_with_onrobot.xacro"
    ]),
    " robot_ip:=192.168.X.X",
    " ur_type:=ur10e",
    " tf_prefix:=robot_",
])
```

### Xacro Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `robot_ip` | `192.168.1.1` | Robot IP address |
| `ur_type` | `ur10e` | UR model (ur3e, ur5e, ur10e, ...) |
| `tf_prefix` | `` | TF prefix for all links |
| `gripper_prefix` | `gripper_` | Prefix for gripper links |
| `use_fake_hardware` | `false` | Enable simulation mode |

## How It Works

1. The **OnRobot URCap** must be installed on the UR controller (via the Teach Pendant)
2. The URCap exposes an **XML-RPC server on port 41414** of the robot's IP
3. This driver connects to that XML-RPC endpoint and calls `system.listMethods` to discover all available gripper methods
4. Based on the available methods, it auto-detects the gripper family (FG, RG, or VG) and configures itself accordingly
5. Commands are sent via XML-RPC **independently of the UR robot program**, meaning the gripper can be controlled in parallel with robot motion

## Package Contents

- `ur_onrobot/` — Python package
  - `UR_onrobot.py` — Low-level XML-RPC helper with auto-discovery
  - `Onrobot_UR_ROS2_driver.py` — ROS 2 node with action server
  - `gripper_joint_state_publisher.py` — Width → joint state converter
  - `gripper_simulator.py` — Fake gripper for simulation
- `urdf/` — Robot + gripper URDF/xacro descriptions
  - `ur_with_onrobot.xacro` — Robot-specific version (requires binary patches, recommended)
  - `ur_with_onrobot_generic.xacro` — Generic version (works with stock packages)
  - `onrobot_2fg14.xacro` — Gripper macro
- `srdf/` — Semantic robot description (collision exclusions)
  - `ur_with_onrobot.srdf.xacro` — Robot-specific SRDF (ur5e_manipulator, ur10e_manipulator)
  - `ur_with_onrobot_generic.srdf.xacro` — Generic SRDF (ur_manipulator)
- `launch/` — Launch files
- `meshes/` — STL files for visualization
- `config/` — Robot-specific controller configurations (ur5e, ur10e)

### URDF/SRDF Variants Explained

**Robot-Specific (Recommended):**
- Uses proper robot names (ur5e, ur10e) matching the actual hardware
- Creates correct MoveIt planning groups (ur5e_manipulator, ur10e_manipulator)
- Eliminates "semantic description mismatch" warnings
- **Requires:** Binary patches to `/opt/ros/humble/share/ur_moveit_config/`
- **Apply patches:** Run the included `apply_binary_patches.sh` script

**Generic (Stock Compatible):**
- Always uses name="ur" regardless of robot type
- Planning group is always "ur_manipulator"
- Works without system modifications
- **Use when:** Shared systems, CI/CD, or cannot modify /opt files

## Tested Hardware

- Universal Robots UR5e, UR10e
- OnRobot 2FG14 gripper
- OnRobot RG6 gripper (driver works, STL meshes not yet included)

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
