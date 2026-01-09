from dimos.core.transport import LCMTransport
from dimos.msgs.sensor_msgs import JointCommand

# Create the publisher
joint_cmd_pub = LCMTransport("/xarm/joint_position_command", JointCommand)

joint_positions_rad_7 = [0, 0, 0, 0, 0, 0, 0]
joint_cmd_pub.broadcast(None, JointCommand(positions=joint_positions_rad_7))