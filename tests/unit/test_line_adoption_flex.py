from services.api.app.application.line_adoption_flex import (
    AiSuitabilityCard,
    MatchReportCard,
    QuestionOption,
    ShelterCard,
    build_ai_suitability_card,
    build_animal_confirm_card,
    build_info_card,
    build_match_report,
    build_question_card,
    build_shelter_carousel,
    build_target_animal_picker,
)


def _pill(box: dict) -> dict:
    """Every tappable row in this module is a bordered `box` with an
    `action` key (not a native `button` component) — see `_pill_row`."""
    assert box["type"] == "box"
    assert "action" in box
    return box


def test_shelter_carousel_wraps_multiple_bubbles_with_select_pill() -> None:
    message = build_shelter_carousel(
        [
            ShelterCard(
                organization_id="org-1",
                name="甲收容所",
                service_area="台北市",
                adoptable_count=5,
                region="north",
            ),
            ShelterCard(
                organization_id="org-2",
                name="乙收容所",
                service_area=None,
                adoptable_count=2,
                region=None,
            ),
        ]
    )
    assert message["type"] == "flex"
    assert message["contents"]["type"] == "carousel"
    bubbles = message["contents"]["contents"]
    assert len(bubbles) == 2
    select_row = _pill(bubbles[0]["body"]["contents"][-1])
    assert "action=select_organization" in select_row["action"]["data"]
    assert "value=org-1" in select_row["action"]["data"]
    assert "地區未提供" in bubbles[1]["body"]["contents"][2]["text"]


def test_single_shelter_is_a_bare_bubble_not_a_carousel() -> None:
    message = build_shelter_carousel(
        [
            ShelterCard(
                organization_id="org-1", name="甲收容所", service_area="台北市", adoptable_count=5
            )
        ]
    )
    assert message["contents"]["type"] == "bubble"


def test_match_report_single_card_has_no_select_pill_by_default() -> None:
    message = build_match_report(
        [
            MatchReportCard(
                animal_id="animal-1",
                name="麻糬",
                shelter_number="A001",
                photo_url="https://example.com/photo.jpg",
                score=75,
                reasons=("體型符合偏好", "與貓咪相容"),
            )
        ]
    )
    bubble = message["contents"]
    assert bubble["type"] == "bubble"
    assert bubble["hero"]["url"] == "https://example.com/photo.jpg"
    assert not any("action" in item for item in bubble["body"]["contents"])
    score_text = next(
        item["text"] for item in bubble["body"]["contents"] if "合拍度" in item.get("text", "")
    )
    assert "75%" in score_text
    reasons_text = next(
        item["text"]
        for item in bubble["body"]["contents"]
        if "體型符合偏好" in item.get("text", "")
    )
    assert "與貓咪相容" in reasons_text


def test_match_report_multi_card_carousel_is_selectable_and_ranked() -> None:
    message = build_match_report(
        [
            MatchReportCard(
                animal_id=f"animal-{i}",
                name=f"狗{i}",
                shelter_number=None,
                photo_url=None,
                score=i * 10,
                reasons=(),
                rank=i,
                selectable=True,
            )
            for i in range(1, 3)
        ]
    )
    bubbles = message["contents"]["contents"]
    assert len(bubbles) == 2
    assert "第 1 名推薦" in bubbles[0]["body"]["contents"][1]["text"]
    select_row = _pill(bubbles[0]["body"]["contents"][-1])
    assert "action=select_matched_animal" in select_row["action"]["data"]
    assert "hero" not in bubbles[0]


def test_match_report_card_select_action_and_label_are_parameterized() -> None:
    """`build_target_animal_picker` reuses the same bubble builder but with a
    different postback action/label than the ranked recommend-me flow."""
    message = build_target_animal_picker(
        [
            MatchReportCard(
                animal_id="animal-1",
                name="麻糬",
                shelter_number="A001",
                photo_url=None,
                selectable=True,
                select_action="select_target_animal",
                select_label="選這隻",
            )
        ]
    )
    bubble = message["contents"]
    select_row = _pill(bubble["body"]["contents"][-1])
    assert "action=select_target_animal" in select_row["action"]["data"]
    assert select_row["contents"][-1]["text"] == "選這隻"
    # No score/reasons were given, so no percentage line should render.
    assert not any("合拍度" in item.get("text", "") for item in bubble["body"]["contents"])


def test_target_animal_picker_caps_at_twelve_bubbles() -> None:
    cards = [
        MatchReportCard(animal_id=f"animal-{i}", name=f"狗{i}", shelter_number=None, photo_url=None)
        for i in range(15)
    ]
    message = build_target_animal_picker(cards)
    assert len(message["contents"]["contents"]) == 12


def test_question_card_renders_progress_bar_and_pill_options() -> None:
    message = build_question_card(
        question_key="housing_type",
        interaction_version=3,
        step=2,
        total=8,
        prompt="你家是什麼樣子呢？🏠",
        options=[
            QuestionOption(code="house", emoji="🏡", label="透天／獨棟房屋"),
            QuestionOption(code="apartment_small", emoji="🏢", label="小坪數公寓"),
        ],
        accent_index=0,
        back_action={"type": "postback", "label": "上一步", "data": "action=back"},
    )
    bubble = message["contents"]
    header_texts = [item["text"] for item in bubble["header"]["contents"] if "text" in item]
    assert any("2 / 8" in text for text in header_texts)
    progress = bubble["header"]["contents"][-1]
    assert progress["contents"][0]["flex"] == 2
    assert progress["contents"][1]["flex"] == 6
    option_row = _pill(bubble["body"]["contents"][0])
    assert "value=house" in option_row["action"]["data"]
    assert "question=housing_type" in option_row["action"]["data"]
    assert "version=3" in option_row["action"]["data"]
    # A back_action was supplied, so a footer nudge box must be appended.
    assert bubble["body"]["contents"][-1]["action"] == {
        "type": "postback",
        "label": "上一步",
        "data": "action=back",
    }


def test_question_card_omits_footer_without_back_action() -> None:
    message = build_question_card(
        question_key="housing_type",
        interaction_version=3,
        step=1,
        total=8,
        prompt="你家是什麼樣子呢？🏠",
        options=[QuestionOption(code="house", emoji="🏡", label="透天／獨棟房屋")],
        accent_index=0,
        back_action=None,
    )
    body_contents = message["contents"]["body"]["contents"]
    assert len(body_contents) == 1


def test_info_card_omits_body_box_when_there_is_no_content() -> None:
    """Regression test: a pure navigational nudge card (no body/rows/actions)
    must not render an empty bordered box under the header — a real bug
    caught live as a blank cream rectangle under the header text."""
    message = build_info_card("請從下方選單選擇想去的地區 🗺️", accent_index=0)
    bubble = message["contents"]
    assert "body" not in bubble
    assert bubble["header"]["cornerRadius"] == "lg"


def test_info_card_renders_body_rows_footer_and_actions() -> None:
    message = build_info_card(
        "領養意願摘要 📋",
        accent_index=2,
        rows=[("居住環境", "🏡 透天／獨棟房屋")],
        footer_note="確認送出前仍可修改。",
        actions=[("📮", "送出", {"type": "postback", "label": "送出", "data": "action=submit"})],
    )
    bubble = message["contents"]
    assert bubble["header"]["cornerRadius"] == "none"
    body_contents = bubble["body"]["contents"]
    assert any(
        "居住環境" in str(item) and "透天" in str(item)
        for item in body_contents
        if item["type"] == "box"
    )
    assert any("確認送出前仍可修改。" in item.get("text", "") for item in body_contents)
    submit_row = _pill(body_contents[-1])
    assert submit_row["action"]["data"] == "action=submit"


def test_animal_confirm_card_has_hero_photo_and_confirm_back_pills() -> None:
    message = build_animal_confirm_card(
        name="麻糬",
        shelter_number="A001",
        photo_url="https://example.com/photo.jpg",
        confirm_action={"type": "postback", "label": "確認是這隻", "data": "action=confirm"},
        back_action={"type": "postback", "label": "不是，重新選一隻", "data": "action=back"},
    )
    bubble = message["contents"]
    assert bubble["hero"]["url"] == "https://example.com/photo.jpg"
    rows = bubble["body"]["contents"]
    confirm_row = _pill(rows[1])
    back_row = _pill(rows[2])
    assert confirm_row["action"]["data"] == "action=confirm"
    assert back_row["action"]["data"] == "action=back"


def test_ai_suitability_card_shows_score_explanation_and_hero_photo() -> None:
    message = build_ai_suitability_card(
        AiSuitabilityCard(
            animal_id="animal-1",
            name="麻糬",
            shelter_number="A001",
            photo_url="https://example.com/photo.jpg",
            score=42,
            explanation="活動力偏高，跟你目前的作息可能需要多花點心力磨合。",
        )
    )
    bubble = message["contents"]
    assert bubble["hero"]["url"] == "https://example.com/photo.jpg"
    texts = [item["text"] for item in bubble["body"]["contents"] if item["type"] == "text"]
    assert any("42%" in text for text in texts)
    assert any("活動力偏高" in text for text in texts)
    assert not any("action" in item for item in bubble["body"]["contents"])


def test_ai_suitability_card_omits_hero_without_photo() -> None:
    message = build_ai_suitability_card(
        AiSuitabilityCard(
            animal_id="animal-1",
            name="麻糬",
            shelter_number=None,
            photo_url=None,
            score=90,
            explanation="非常適合！",
        )
    )
    assert "hero" not in message["contents"]


def test_animal_confirm_card_omits_hero_without_photo() -> None:
    message = build_animal_confirm_card(
        name="麻糬",
        shelter_number=None,
        photo_url=None,
        confirm_action={"type": "postback", "label": "確認是這隻", "data": "action=confirm"},
        back_action={"type": "postback", "label": "不是，重新選一隻", "data": "action=back"},
    )
    assert "hero" not in message["contents"]
