"""诊断工具：查看 BGE-reranker 对「相关 / 弱相关 / 不相关」文本对的分数分布。

用途：调整 ``RAG_MIN_RELEVANCE``（有效上下文的相关性下限）前，先用本脚本了解
当前模型的实际分数区间，避免凭感觉设阈值——阈值直接决定知识缺口识别的灵敏度。

用法::

    cd backend
    uv run python -m scripts.diag_rerank_scores
"""

from __future__ import annotations

from app.utils import rerank_client

DOCS = [
    "一线城市住宿每晚不超过 500 元，二线城市不超过 350 元。",
    "签收后 7 天内可无理由退货；生鲜破损可在 24 小时内申请赔付。",
    "高管年度基本薪酬区间为 120 万元至 200 万元。",
]

CASES = [
    ("强相关", "出差住宿标准是多少？"),
    ("弱相关", "海外直邮清关延误怎么处理？"),
    ("不相关", "公司年会计划安排在什么时候？"),
]


def main() -> None:
    print(f"候选片段（{len(DOCS)} 条），分数越高越相关：\n")
    for label, query in CASES:
        scores = rerank_client.rerank(query, DOCS)
        print(f"[{label}] {query}")
        for doc, score in zip(DOCS, scores):
            print(f"        {score:6.4f}  {doc[:26]}…")
        print()


if __name__ == "__main__":
    main()
