"""Shared Isaac collection with strict v88 release checks in parent and child."""
import argparse
import sys
from workflows import protocol_v88
from workflows.collect_disturbance_data_v86 import main as shared_main
from workflows.disturbance_data_v88 import verify_manifest


def main():
    parser=argparse.ArgumentParser(add_help=False);parser.add_argument('--manifest',required=True)
    args,_=parser.parse_known_args();verify_manifest(args.manifest)
    return shared_main(spec=protocol_v88)


if __name__=='__main__':sys.exit(main())
