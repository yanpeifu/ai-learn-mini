"""闯关接口端到端测试（PRD Q1–Q6）。"""

from app.repositories import QuestionRepository
from app.services.llm.base import LLMBadFormatError
from httpx import AsyncClient
from tests.fakes import ScriptedProvider, make_question_set, outline_payload
from tests.task_utils import enqueue_levels, wait_for_task

VALID_TEXT = "存款准备金率是商业银行按规定向央行缴存的准备金占其存款总额的比例，提高准备金率会减少可放贷资金。"


async def _prepare_outline(auth_client: AsyncClient, provider: ScriptedProvider) -> int:
    provider.responses.append(outline_payload())
    created = await auth_client.post("/api/knowledge/outline", json={"raw_text": VALID_TEXT})
    outline_id = created.json()["data"]["outline_id"]
    provider.responses.append(make_question_set())
    task = await enqueue_levels(auth_client, outline_id)
    assert task["status"] == "succeeded", task
    return outline_id


async def test_start_attempt_returns_levels_without_answers(
    auth_client: AsyncClient, provider: ScriptedProvider
) -> None:
    outline_id = await _prepare_outline(auth_client, provider)

    response = await auth_client.post("/api/attempt/start", json={"outline_id": outline_id})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total_count"] == 15
    assert data["status"] == "ongoing"
    assert [level["seq"] for level in data["levels"]] == [1, 2, 3]
    assert "explanation" not in response.text


async def test_answer_returns_judgment_and_explanation(
    auth_client: AsyncClient, provider: ScriptedProvider, db_session
) -> None:  # noqa: ANN001
    outline_id = await _prepare_outline(auth_client, provider)
    start = await auth_client.post("/api/attempt/start", json={"outline_id": outline_id})
    attempt_id = start.json()["data"]["attempt_id"]
    question_public = start.json()["data"]["levels"][0]["questions"][0]
    question = QuestionRepository(db_session).get(question_public["id"])

    response = await auth_client.post(
        f"/api/attempt/{attempt_id}/answer",
        json={"question_id": question.id, "answer": list(question.answer_json), "elapsed_ms": 4200},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["is_correct"] is True
    assert data["correct_answer"] == list(question.answer_json)
    assert data["explanation"]
    assert data["answered_count"] == 1
    assert data["combo"] == 1
    assert data["already_answered"] is False


async def test_wrong_answer_records_mistake_and_duplicate_is_rejected(
    auth_client: AsyncClient, provider: ScriptedProvider, db_session
) -> None:  # noqa: ANN001
    outline_id = await _prepare_outline(auth_client, provider)
    start = await auth_client.post("/api/attempt/start", json={"outline_id": outline_id})
    attempt_id = start.json()["data"]["attempt_id"]
    question_public = start.json()["data"]["levels"][0]["questions"][0]
    question = QuestionRepository(db_session).get(question_public["id"])
    wrong = [key for key in ("A", "B", "C", "D") if key not in question.answer_json][:1]

    first = await auth_client.post(
        f"/api/attempt/{attempt_id}/answer",
        json={"question_id": question.id, "answer": wrong, "elapsed_ms": 2000},
    )
    second = await auth_client.post(
        f"/api/attempt/{attempt_id}/answer",
        json={"question_id": question.id, "answer": list(question.answer_json), "elapsed_ms": 2000},
    )

    assert first.json()["data"]["is_correct"] is False
    assert second.json()["data"]["is_correct"] is False  # 提交后不可更改
    assert second.json()["data"]["already_answered"] is True


async def test_answer_for_unknown_question_returns_404(
    auth_client: AsyncClient, provider: ScriptedProvider
) -> None:
    outline_id = await _prepare_outline(auth_client, provider)
    start = await auth_client.post("/api/attempt/start", json={"outline_id": outline_id})
    attempt_id = start.json()["data"]["attempt_id"]

    response = await auth_client.post(
        f"/api/attempt/{attempt_id}/answer",
        json={"question_id": 999999, "answer": ["A"], "elapsed_ms": 100},
    )

    assert response.status_code == 404
    assert response.json()["code"] == "QUESTION_NOT_FOUND"


async def _answer_all(
    client: AsyncClient,
    attempt_id: int,
    levels: list[dict],
    db_session,  # noqa: ANN001
    *,
    correct: bool = True,
) -> None:
    for level in levels:
        for item in level["questions"]:
            question = QuestionRepository(db_session).get(item["id"])
            answer = list(question.answer_json)
            if not correct:
                answer = [key for key in ("A", "B", "C", "D") if key not in answer][:1]
            response = await client.post(
                f"/api/attempt/{attempt_id}/answer",
                json={"question_id": question.id, "answer": answer, "elapsed_ms": 3000},
            )
            assert response.status_code == 200, response.text


async def test_finish_returns_settlement_and_history(
    auth_client: AsyncClient, provider: ScriptedProvider, db_session
) -> None:  # noqa: ANN001
    outline_id = await _prepare_outline(auth_client, provider)
    start = await auth_client.post("/api/attempt/start", json={"outline_id": outline_id})
    attempt_id = start.json()["data"]["attempt_id"]
    await _answer_all(auth_client, attempt_id, start.json()["data"]["levels"], db_session)

    finish = await auth_client.post(f"/api/attempt/{attempt_id}/finish")
    history = await auth_client.get("/api/attempts")
    ongoing = await auth_client.get("/api/attempt/ongoing")

    assert finish.status_code == 200
    data = finish.json()["data"]
    assert data["accuracy"] == 100.0
    assert data["star"] == 3
    assert data["correct_count"] == 15
    assert data["status"] == "finished"
    assert len(data["points"]) == 3
    assert data["weak_points"] == []

    assert history.json()["data"]["total"] == 1
    assert history.json()["data"]["list"][0]["star"] == 3
    assert ongoing.json()["data"]["attempt"] is None


async def test_low_score_settlement_has_weak_points_and_advice(
    auth_client: AsyncClient, provider: ScriptedProvider, db_session
) -> None:  # noqa: ANN001
    outline_id = await _prepare_outline(auth_client, provider)
    start = await auth_client.post("/api/attempt/start", json={"outline_id": outline_id})
    attempt_id = start.json()["data"]["attempt_id"]
    await _answer_all(
        auth_client, attempt_id, start.json()["data"]["levels"], db_session, correct=False
    )

    finish = await auth_client.post(f"/api/attempt/{attempt_id}/finish")

    data = finish.json()["data"]
    assert data["accuracy"] == 0.0
    assert data["star"] == 0
    assert data["weak_points"]
    # 0 星走安抚文案（原型 P4-2 的语气），并把落点引向错题
    assert "先看看错题" in data["advice"]
    assert "0 / 15" in data["advice"]


async def test_finish_is_idempotent(
    auth_client: AsyncClient, provider: ScriptedProvider, db_session
) -> None:  # noqa: ANN001
    outline_id = await _prepare_outline(auth_client, provider)
    start = await auth_client.post("/api/attempt/start", json={"outline_id": outline_id})
    attempt_id = start.json()["data"]["attempt_id"]
    await _answer_all(auth_client, attempt_id, start.json()["data"]["levels"], db_session)

    first = await auth_client.post(f"/api/attempt/{attempt_id}/finish")
    second = await auth_client.post(f"/api/attempt/{attempt_id}/finish")
    answer_after_finish = await auth_client.post(
        f"/api/attempt/{attempt_id}/answer",
        json={"question_id": start.json()["data"]["levels"][0]["questions"][0]["id"], "answer": ["A"]},
    )

    assert first.json()["data"] == second.json()["data"]
    assert answer_after_finish.status_code == 409
    assert answer_after_finish.json()["code"] == "ATTEMPT_FINISHED"


async def test_result_detail_contains_user_answers_for_readonly_review(
    auth_client: AsyncClient, provider: ScriptedProvider, db_session
) -> None:  # noqa: ANN001
    outline_id = await _prepare_outline(auth_client, provider)
    start = await auth_client.post("/api/attempt/start", json={"outline_id": outline_id})
    attempt_id = start.json()["data"]["attempt_id"]
    levels = start.json()["data"]["levels"]
    await _answer_all(auth_client, attempt_id, levels, db_session)
    await auth_client.post(f"/api/attempt/{attempt_id}/finish")

    detail = await auth_client.get(f"/api/attempt/{attempt_id}")

    data = detail.json()["data"]
    assert data["attempt"]["status"] == "finished"
    assert data["settlement"]["star"] == 3
    first_question = data["levels"][0]["questions"][0]
    assert first_question["answered"] is True
    assert first_question["user_answer"]
    assert first_question["explanation"]


async def test_ongoing_attempt_supports_resume(
    auth_client: AsyncClient, provider: ScriptedProvider, db_session
) -> None:  # noqa: ANN001
    outline_id = await _prepare_outline(auth_client, provider)
    start = await auth_client.post("/api/attempt/start", json={"outline_id": outline_id})
    attempt_id = start.json()["data"]["attempt_id"]
    levels = start.json()["data"]["levels"]
    question = QuestionRepository(db_session).get(levels[0]["questions"][0]["id"])
    await auth_client.post(
        f"/api/attempt/{attempt_id}/answer",
        json={"question_id": question.id, "answer": list(question.answer_json), "elapsed_ms": 1000},
    )

    ongoing = await auth_client.get("/api/attempt/ongoing")

    data = ongoing.json()["data"]["attempt"]
    assert data["attempt_id"] == attempt_id
    assert data["answered_count"] == 1
    assert data["next_question_id"] == levels[0]["questions"][1]["id"]


async def test_ongoing_attempt_does_not_leak_answers(
    auth_client: AsyncClient, provider: ScriptedProvider, db_session
) -> None:  # noqa: ANN001
    """未作答的题目不能返回答案与讲解，否则抓包就能作弊。"""
    outline_id = await _prepare_outline(auth_client, provider)
    start = await auth_client.post("/api/attempt/start", json={"outline_id": outline_id})
    attempt_id = start.json()["data"]["attempt_id"]

    detail = await auth_client.get(f"/api/attempt/{attempt_id}")

    first_question = detail.json()["data"]["levels"][0]["questions"][0]
    assert first_question["answered"] is False
    assert first_question["correct_answer"] == []
    assert first_question["explanation"] == ""

    # 作答之后，该题才返回答案与讲解
    question_public = start.json()["data"]["levels"][0]["questions"][0]
    question = QuestionRepository(db_session).get(question_public["id"])
    await auth_client.post(
        f"/api/attempt/{attempt_id}/answer",
        json={"question_id": question.id, "answer": ["A"], "elapsed_ms": 1000},
    )
    detail_after = await auth_client.get(f"/api/attempt/{attempt_id}")
    answered = detail_after.json()["data"]["levels"][0]["questions"][0]

    assert answered["answered"] is True
    assert answered["correct_answer"] == list(question.answer_json)
    assert answered["explanation"]


async def test_starting_new_attempt_abandons_the_previous_one(
    auth_client: AsyncClient, provider: ScriptedProvider
) -> None:
    outline_id = await _prepare_outline(auth_client, provider)
    first = await auth_client.post("/api/attempt/start", json={"outline_id": outline_id})
    second = await auth_client.post("/api/attempt/start", json={"outline_id": outline_id})

    ongoing = await auth_client.get("/api/attempt/ongoing")

    assert first.json()["data"]["attempt_id"] != second.json()["data"]["attempt_id"]
    assert ongoing.json()["data"]["attempt"]["attempt_id"] == second.json()["data"]["attempt_id"]


async def test_other_users_attempt_is_not_visible(
    auth_client: AsyncClient, client: AsyncClient, provider: ScriptedProvider
) -> None:
    outline_id = await _prepare_outline(auth_client, provider)
    start = await auth_client.post("/api/attempt/start", json={"outline_id": outline_id})
    attempt_id = start.json()["data"]["attempt_id"]
    login = await client.post("/api/auth/login", json={"code": "dev_intruder"})
    headers = {"Authorization": f"Bearer {login.json()['data']['token']}"}

    response = await client.get(f"/api/attempt/{attempt_id}", headers=headers)

    assert response.status_code == 404
    assert response.json()["code"] == "ATTEMPT_NOT_FOUND"


async def test_start_requires_existing_outline(auth_client: AsyncClient) -> None:
    response = await auth_client.post("/api/attempt/start", json={"outline_id": 999999})

    assert response.status_code == 404


async def test_llm_failure_during_levels_does_not_create_attempt(
    auth_client: AsyncClient, provider: ScriptedProvider
) -> None:
    provider.responses.append(outline_payload())
    created = await auth_client.post("/api/knowledge/outline", json={"raw_text": VALID_TEXT})
    outline_id = created.json()["data"]["outline_id"]
    provider.responses.extend([LLMBadFormatError("坏 JSON")] * 3)

    queued = await auth_client.post("/api/knowledge/levels", json={"outline_id": outline_id})
    task = await wait_for_task(auth_client, queued.json()["data"]["task_id"])
    start = await auth_client.post("/api/attempt/start", json={"outline_id": outline_id})

    assert task["status"] == "failed"
    assert task["error_code"] == "LLM_BAD_FORMAT"
    assert start.status_code == 502  # 没有题目就不允许开始闯关
