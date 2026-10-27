"""
大模型客户端（OpenAI 兼容接口）

- 真实模式：调用 DeepSeek / Qwen 等 OpenAI 兼容 API；
- mock 模式：离线模板响应，供冒烟测试与流水线联调（不消耗 API）。
"""
import json
import os
import re


class LLMClient:
    def __init__(self, base_url: str, api_key: str, model: str,
                 temperature: float = 0.2, mock: bool = False,
                 max_output_tokens: int | None = None):
        if max_output_tokens is not None and (not isinstance(max_output_tokens, int)
                                              or isinstance(max_output_tokens, bool)
                                              or max_output_tokens < 1):
            raise ValueError("max_output_tokens must be a positive integer")
        self.model = model
        self.temperature = temperature
        self.mock = mock
        self.max_output_tokens = max_output_tokens
        self.last_response_metadata: dict = {"mock": bool(mock)}
        self.last_response_text: str | None = None
        self.last_raw_response: dict | None = None
        self.last_request: dict | None = None
        if not mock:
            from openai import OpenAI
            if not api_key:
                raise ValueError("真实模式需要设置环境变量 LLM_API_KEY")
            self._client = OpenAI(base_url=base_url, api_key=api_key)

    # ---------- 调用 ----------
    def chat(self, prompt: str, system: str | None = None) -> str:
        self.last_response_text = None
        self.last_raw_response = None
        self.last_request = None
        self.last_response_metadata = {"mock": bool(self.mock)}
        if self.mock:
            self.last_response_metadata = {"mock": True}
            self.last_response_text = self._mock_response(prompt)
            return self.last_response_text
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        request = {"model": self.model, "messages": messages,
                   "temperature": self.temperature}
        if self.max_output_tokens is not None:
            request["max_tokens"] = self.max_output_tokens
        self.last_request = request
        resp = self._client.chat.completions.create(**request)
        # Save the SDK data object, not HTTP request headers or credentials.
        self.last_raw_response = resp.model_dump(mode="json")
        usage = getattr(resp, "usage", None)
        self.last_response_metadata = {
            "mock": False,
            "request_id": getattr(resp, "_request_id", None),
            "response_model": getattr(resp, "model", None),
            "system_fingerprint": getattr(resp, "system_fingerprint", None),
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
            "finish_reason": resp.choices[0].finish_reason,
            "requested_max_output_tokens": self.max_output_tokens,
        }
        self.last_response_text = resp.choices[0].message.content
        return self.last_response_text

    # ---------- 离线模板响应 ----------
    def _mock_response(self, prompt: str) -> str:
        if "judge" in prompt[:200] or "评审专家" in prompt[:200]:
            return json.dumps({"faithfulness": 4, "coverage": 4,
                               "professionalism": 4, "comment": "mock judge"},
                              ensure_ascii=False)
        annual_ids = re.findall(r"^\[(A\d+)\]", prompt, re.MULTILINE)
        regulation_ids = re.findall(r"^\[(R\d+)\]", prompt, re.MULTILINE)
        if annual_ids and regulation_ids:
            annual_id, regulation_id = annual_ids[0], regulation_ids[0]
            return json.dumps({
                "evaluation": (
                    f"（mock，仅用于检查来源链路）检索上下文包含年报证据 {annual_id} "
                    f"和法规证据 {regulation_id}；这不是对公司表现或法规适用性的事实判断。"
                    f"【年报依据：[{annual_id}]】【法规依据：[{regulation_id}]】"),
                "claims": [{"claim": "检索上下文中存在对应来源片段",
                            "evidence_status": "supported",
                            "evidence_ids": [annual_id, regulation_id]}],
                "citations": [{"evidence_id": annual_id, "used_for": "来源链路冒烟检查"},
                              {"evidence_id": regulation_id, "used_for": "来源链路冒烟检查"}],
                "overall_evidence_status": "partial",
                "mock": True,
            }, ensure_ascii=False)
        # 从提示词中提取第一条法规编号，生成带引用的模板评价
        # 注：法规标题可能含《》（如"【第215号令】《XX办法》"），故匹配至 "》（来源）" 边界
        m = re.search(r"\[1\] 《(.+)》 ?（", prompt)
        title = m.group(1) if m else "上市公司信息披露管理办法"
        if " 第" in title:
            # 提示词行内带条款号：拆出真实条款号
            title_part, clause_part = title.split(" 第", 1)
            clause = "第" + clause_part
        else:
            # 无条款号信息：clause 置 None（对齐时按法规名匹配），不编造条款
            title_part, clause = title, None
        citation = {"title": title_part, "clause": clause, "used_for": "mock 引用"}
        clause_txt = citation["clause"] or ""
        return json.dumps({
            "evaluation": f"（mock）依据《{citation['title']}》{clause_txt}，"
                          f"该公司相关自律表现总体合规。【依据：《{citation['title']}》{clause_txt}】",
            "strengths": ["mock 优势"], "weaknesses": ["mock 不足"],
            "score": 80, "citations": [citation],
        }, ensure_ascii=False)


def parse_json(text: str) -> dict:
    """稳健解析模型输出的 JSON"""
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    else:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            text = m.group(0)
    return json.loads(text)
