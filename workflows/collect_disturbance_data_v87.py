"""Shared Isaac collector with the fixed larger-motion protocol."""
import sys
from workflows.collect_disturbance_data_v86 import main
from workflows import protocol_v87

if __name__=='__main__':sys.exit(main(spec=protocol_v87))
