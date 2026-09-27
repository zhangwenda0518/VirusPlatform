"""PAmiRDB 植物抗病毒 miRNA 靶标预测引擎（移植包）。

7 个文件原样移植自独立项目 12.pamirdb（PAmiRDB，scripts/alignment.py、
psrnatarget.py、psrobot.py、rnahybrid.py、rna22.py、tapir.py、consensus.py，
2026-09-18 移植）。引擎打分口径与 PAmiRDB 线上版保持一致，**不要单独改动
单个引擎的打分/过滤阈值**——需要调参时先对照 http://39.106.101.94/pamirdb/
的线上行为，否则共识等级（LOW→VERY HIGH）会与线上库不可比。

与原版的差异（仅两处，逻辑不变）：
  1. consensus.py 的兄弟模块导入改为包内相对导入优先（保持独立脚本运行兼容）；
  2. consensus.py to_dict() 补导出 psrobot 字段（原版 ConsensusResult 里有
     psrobot 结果但 to_dict 漏导出，前端算法表会永远显示 psRobot SKIP）。

对外入口：run_consensus_prediction / to_dict / align_mirna_to_target。
"""

from .consensus import (
    ConsensusResult,
    ENGINE_KEYS,
    run_consensus_prediction,
    to_dict,
    stratified_consensus,
)
from .alignment import AlignmentResult, align_mirna_to_target

__all__ = [
    'ConsensusResult', 'run_consensus_prediction', 'to_dict',
    'stratified_consensus', 'AlignmentResult', 'align_mirna_to_target',
    'ENGINE_KEYS',
]
