import os
import launch
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
from webots_ros2_driver.utils import controller_url_prefix
from webots_ros2_driver.webots_launcher import WebotsLauncher
from launch.event_handlers import OnProcessExit
from launch.actions import RegisterEventHandler, DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, Command
from launch.conditions import LaunchConfigurationEquals
from launch.actions import OpaqueFunction

def evaluate_robot_name(context, *args, **kwargs):
    robot_name = LaunchConfiguration('robot_name').perform(context=context)
    package_dir = get_package_share_directory('webots_ros2_husarion')

    rosbot_description_package =  get_package_share_directory(robot_name + '_description')
    rosbot_description = os.path.join(rosbot_description_package, 'urdf', robot_name + '.urdf.xacro')

    xacro_args = ' use_sim:=true simulation_engine:=webots'
    if robot_name == 'rosbot_xl':
        xacro_args += ' mecanum:=true lidar_model:=slamtec_rplidar_a2'

    rosbot_description_urdf = Command(['xacro ', rosbot_description, xacro_args])

    rosbot_state_publisher = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        output='screen',
        parameters=[
            {'robot_description': rosbot_description_urdf},
            {'use_sim_time': True},
        ],
    )

    world = WebotsLauncher(
        world=os.path.join(package_dir, 'worlds', robot_name + '.wbt'),
        ros2_supervisor=True
    )

    rosbot_ros2_control_params = os.path.join(
        package_dir, 'resource', robot_name+ '_controllers.yaml')

    rosbot_webots_robot_driver = Node(
        package='webots_ros2_driver',
        executable='driver',
        additional_env={'WEBOTS_CONTROLLER_URL': controller_url_prefix() + robot_name},
        output='screen',
        parameters=[
            {'robot_description': rosbot_description_urdf},
            {'set_robot_state_publisher': True},
            {'use_sim_time': True},
            rosbot_ros2_control_params,
        ],
        remappings=[
            (robot_name + "_base_controller/cmd_vel_unstamped", "cmd_vel"),
            ("odom", robot_name + "_base_controller/odom"),
            (robot_name + "/laser", '/scan'),
            (robot_name + "/rl_range", '/range/rl'),
            (robot_name + "/rr_range", '/range/rr'),
            (robot_name + "/fl_range", '/range/fl'),
            (robot_name + "/fr_range", '/range/fr'),
        ]
    )

    joint_state_broadcaster_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=[
            "joint_state_broadcaster",
            "--controller-manager",
            "/controller_manager",
            "--controller-manager-timeout",
            "120",
        ],
    )

    robot_controller_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=[
            robot_name + "_base_controller",
            "--controller-manager",
            "/controller_manager",
            "--controller-manager-timeout",
            "120",
        ],
    )

    # Delay start of robot_controller after joint_state_broadcaster
    delay_robot_controller_spawner_after_joint_state_broadcaster_spawner = (
        RegisterEventHandler(
            event_handler=OnProcessExit(
                target_action=joint_state_broadcaster_spawner,
                on_exit=[robot_controller_spawner],
            )
        )
    )
    return [
        world,
        world._supervisor,
        rosbot_webots_robot_driver,
        RegisterEventHandler(
                        event_handler=launch.event_handlers.OnProcessExit(
                            target_action=world._supervisor,
                            on_exit=[launch.actions.EmitEvent(
                                event=launch.events.Shutdown())],
                        )
        ),
        joint_state_broadcaster_spawner,
        delay_robot_controller_spawner_after_joint_state_broadcaster_spawner,
        rosbot_state_publisher
    ]

def generate_launch_description():
    package_dir = get_package_share_directory('webots_ros2_husarion')

    laser_filter_node = Node(
        package="laser_filters",
        executable="scan_to_scan_filter_chain",
        parameters=[ os.path.join(package_dir, 'resource', 'laser_filter.yaml')],
        condition=LaunchConfigurationEquals('robot_name', 'rosbot_xl')
    )

    ekf_config = os.path.join(
        package_dir, 'resource', 'ekf.yaml')

    robot_localization_node = Node(
        package='robot_localization',
        executable='ekf_node',
        name='ekf_filter_node',
        output='screen',
        parameters=[
            ekf_config,
            {'use_sim_time': True}
        ]
    )

    # Standard ROS 2 launch description
    return launch.LaunchDescription([
        DeclareLaunchArgument(name='use_sim_time', default_value='True',
                                            description='Flag to enable use_sim_time'),
        DeclareLaunchArgument(name='robot_name', default_value='rosbot',
                                            description='Spawned robot name'),
        laser_filter_node,
        robot_localization_node,

        # Used to get robot name as string
        OpaqueFunction(function=evaluate_robot_name),
    ])