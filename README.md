# EasyUUV-Isaac-Simulation

[![WebSite](https://img.shields.io/badge/Github_Page-PDF-77DDFF.svg)](https://360zmem.github.io/easyuuv/) [![WebSite](https://img.shields.io/github/last-commit/360ZMEM/EasyUUV-Isaac-Simulation?color=green)](https://github.com/360ZMEM/EasyUUV-Isaac-Simulation)

This repository contains code implementation for simulator of the paper "EasyUUV: An LLM-Enhanced Universal and Lightweight Sim-to-Real Reinforcement Learning Framework for UUV Attitude Control".

## 当前研究入口

本分支研究冻结物理模型、完整提升 Koopman 及两者结合的预测与控制。v87已完成扩大训练和独立预测/求解比较：结合模型测试16/16窗口通过，纯Koopman4/16；原闭环准入未通过，按用户决定不运行闭环，`no_selection`保留。

- [研究索引与历史结论](docs/phase9_research_index.md)：从这里定位当前协议、结果、代码和历史报告。
- [当前状态](.planning/STATE.md)：正在执行什么、哪些证据尚未取得。
- [项目边界](.planning/PROJECT.md)与[控制链合同](docs/phase9_control_chain_contract.md)：研究目标、完整提升传播及共同控制接口。
- [v87运行说明](docs/phase9_diverse_v87_runbook.md)：本轮数据、冻结、验证和服务器运行规则。

当前验证环境为 Isaac Sim 5.0 + Isaac Lab 2.2.1；主服务器为 `suanliyun-agentic-AUV`。下方上游 Isaac Lab 1.x 部署、训练和硬件链接保留为历史资料，不代表本分支已经取得硬件或当前 Koopman 控制效果。旧交接与规划通过研究索引查阅。

## 上游项目与部署资料（历史）

The hardware deployment code repository refers to [**HERE**](https://github.com/360ZMEM/EasyUUV-UUV-Deploy)

![intro](README.assets/intro.png)

## Simulator Deployment

### Environment Setup

This project utilizes a simulator based on Isaac Sim/Lab. The code has been tested on a system with NVIDIA GeForce RTX 4060 (requiring approximately 5600MB GPU memory for 2048 parallel environments), Ubuntu 24.04 LTS, IsaacSim v4.0.0, and IsaacLab v1.0.0 (installation instructions are provided based on this configuration). Theoretically, the code should also work with other Isaac Lab V1 versions such as IsaacSim v4.2.0 + IsaacLab v1.4.1. For migration to IsaacLab V2, please refer to [this link](https://isaac-sim.github.io/IsaacLab/main/source/refs/migration.html).

First, you should [download Isaac Sim](https://docs.isaacsim.omniverse.nvidia.com/4.5.0/installation/download.html) and confirm version 4.0.0 is selected. Next, install Isaac Lab v1.0.0 using:

```bash
git clone --branch v1.0.0 https://github.com/isaac-sim/IsaacLab.git
```

To ensure compatibility with RSL-RL, modify the file `<IsaacLab_Path>/source/extensions/omni.isaac.lab_tasks/setup.py` following [these instructions](https://github.com/isaac-sim/IsaacLab/pull/1808/files/8af43cb048cdaa976c24a0f2b569ea9e45db533d) before installation. Then follow the [Isaac Lab installation guide](https://isaac-sim.github.io/IsaacLab/v1.4.1/source/setup/installation/binaries_installation.html) to complete the setup and verify functionality through tests.

### Deployment Configuration

Create a symbolic link or copy the directory to install the reinforcement learning environment:

```bash
git clone https://github.com/360ZMEM/EasyUUV-Isaac-Simulation.git
ln -s EasyUUV-Isaac-Simulation <IsaacLab_Path>/source/extensions/omni.isaac.lab_tasks/omni/isaac/lab_tasks/direct/EasyUUV-Isaac-Simulation
```

### Training

Train using the following command (ensure correct Python environment activation and execution from IsaacLab root directory; `--headless` flag is recommended for improved performance):

```bash
./isaaclab.sh -p source/standalone/workflows/rsl_rl/train.py --task EasyUUV-Direct-v1 --num_envs 1024 --headless
```

Note that when visualization is enabled, loading USD files consumes significant memory. Therefore, if the `--headless` option is not specified, you should reduce the `--num_envs` parameter (e.g., to 512); otherwise, it may lead to excessive resource usage or crashes.

Monitor training with Tensorboard:

```bash
tensorboard --logdir <IsaacLab_Path>/logs/rsl_rl/EasyUUV-Isaac-Simulation/
```

Generated policy checkpoints can be exported to Torch JIT/ONNX formats using:

```bash
./isaaclab.sh -p <IsaacLab_Path>/source/extensions/omni.isaac.lab_tasks/omni/isaac/lab_tasks/direct/EasyUUV-Isaac-Simulation/workflows/gen_policy.py
```

Exported files will be saved at `<IsaacLab_Path>/logs/rsl_rl/EasyUUV-Isaac-Simulation/<latest_date>/exported/policy.pt` (contains both Torch JIT and ONNX formats). Load Torch JIT models with `torch.jit.load()`. Note that RSL-RL creates date-stamped folders for each training session, where `<latest_date>` represents the most recent timestamp folder.

### Evaluation

The `workflows` directory contains trajectory tracking implementations. For example:

```bash
./isaaclab.sh -p <IsaacLab_Path>/source/extensions/omni.isaac.lab_tasks/omni/isaac/lab_tasks/direct/EasyUUV-Isaac-Simulation/workflows/play_eval_task1.py
```

- `play_eval.py`: Tracks sinusoidal signals.
- `play_eval_task2.py`: Tracks irregular dynamic signals.
- `play_eval_step.py`: Tracks step signals.
- `play_controller.py`: Direct controller implementation (w/o RL).

Note: Requires prior configuration of `wandb` for real-time visualization. Also, we provide offline file for tracking result: `<IsaacLab_Path>/source/results/rsl_rl/EasyUUV-Isaac-Simulation/.*/model_.*_play/logs.csv`.

## Acknowledgement

This repository is modified based on [this codebase](https://github.com/warplab/isaac-auv-env).

# Cite

If you find it useful for your work please cite:

```bibtex
@article{xie2025easyuuv,
      title={EasyUUV: An LLM-Enhanced Universal and Lightweight Sim-to-Real Reinforcement Learning Framework for UUV Attitude Control},
      author={Xie, Guanwen and Xu, Jingzehua and Tang, Jiwei and Huang, Yubo and Zhang, Shuai and Li, Xiaofan},
      journal={arXiv preprint arXiv:2510.22126},
      year={2025}
    }
```
