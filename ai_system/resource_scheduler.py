"""
Simple GPU resource scheduler for mapping investors to GPU pools and founders to GPUs.
"""

import logging
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class InvestorGpuPool:
    investor_id: str
    owned_gpu_ids: List[int]
    allocations: Dict[str, List[int]] = field(default_factory=dict)

    @property
    def free_gpu_ids(self) -> List[int]:
        used = set()
        for gpu_ids in self.allocations.values():
            used.update(gpu_ids)
        return [gpu_id for gpu_id in self.owned_gpu_ids if gpu_id not in used]


class ResourceScheduler:
    def __init__(self, physical_gpu_ids: Optional[List[int]] = None):
        if physical_gpu_ids is None:
            try:
                from ai_scientist.treesearch.parallel_agent import get_gpu_count

                physical_gpu_ids = list(range(get_gpu_count()))
            except Exception:
                physical_gpu_ids = []
        self.physical_gpu_ids = list(physical_gpu_ids)
        self._pools: Dict[str, InvestorGpuPool] = {}
        self._cursor = 0
        self._lock = threading.Lock()

    def assign_investor_pool(self, investor_id: str, num_gpus: int) -> List[int]:
        with self._lock:
            if investor_id in self._pools:
                return self._pools[investor_id].owned_gpu_ids

            available = self.physical_gpu_ids[self._cursor :]
            if len(available) < num_gpus:
                logger.warning(
                    f"[ResourceScheduler] GPU 不足，{investor_id} 请求 {num_gpus}，仅剩 {len(available)}"
                )
                num_gpus = len(available)

            assigned = self.physical_gpu_ids[self._cursor : self._cursor + num_gpus]
            self._cursor += num_gpus
            self._pools[investor_id] = InvestorGpuPool(
                investor_id=investor_id,
                owned_gpu_ids=list(assigned),
            )
            return assigned

    def allocate_to_founder(
        self, investor_id: str, founder_id: str, num_gpus: int = 1
    ) -> List[int]:
        with self._lock:
            pool = self._pools.get(investor_id)
            if pool is None or num_gpus <= 0:
                return []
            free = pool.free_gpu_ids
            if not free:
                return []
            allocated = free[:num_gpus]
            pool.allocations[founder_id] = list(allocated)
            return allocated

    def release_from_founder(self, investor_id: str, founder_id: str):
        with self._lock:
            pool = self._pools.get(investor_id)
            if pool is None:
                return
            pool.allocations.pop(founder_id, None)

    def status(self) -> dict:
        with self._lock:
            return {
                "physical": self.physical_gpu_ids,
                "pools": {
                    investor_id: {
                        "owned": pool.owned_gpu_ids,
                        "free": pool.free_gpu_ids,
                        "allocations": dict(pool.allocations),
                    }
                    for investor_id, pool in self._pools.items()
                },
            }
