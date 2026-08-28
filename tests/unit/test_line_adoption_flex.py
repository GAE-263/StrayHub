from services.api.app.application.line_adoption_flex import (
    MatchReportCard,
    ShelterCard,
    build_match_report,
    build_shelter_carousel,
)


def test_shelter_carousel_wraps_multiple_bubbles_with_select_button() -> None:
    message = build_shelter_carousel(
        [
            ShelterCard(
                organization_id="org-1", name="甲收容所", service_area="台北市", adoptable_count=5
            ),
            ShelterCard(
                organization_id="org-2", name="乙收容所", service_area=None, adoptable_count=2
            ),
        ]
    )
    assert message["type"] == "flex"
    assert message["contents"]["type"] == "carousel"
    bubbles = message["contents"]["contents"]
    assert len(bubbles) == 2
    first_button = bubbles[0]["body"]["contents"][-1]
    assert first_button["type"] == "button"
    assert "action=select_organization" in first_button["action"]["data"]
    assert "value=org-1" in first_button["action"]["data"]
    assert "地區未提供" in bubbles[1]["body"]["contents"][1]["text"]


def test_single_shelter_is_a_bare_bubble_not_a_carousel() -> None:
    message = build_shelter_carousel(
        [
            ShelterCard(
                organization_id="org-1", name="甲收容所", service_area="台北市", adoptable_count=5
            )
        ]
    )
    assert message["contents"]["type"] == "bubble"


def test_match_report_single_card_has_no_select_button_by_default() -> None:
    message = build_match_report(
        [
            MatchReportCard(
                animal_id="animal-1",
                name="麻糬",
                shelter_number="A001",
                photo_url="https://example.com/photo.jpg",
                score=6.0,
                reasons=("體型符合偏好", "與貓咪相容"),
            )
        ]
    )
    bubble = message["contents"]
    assert bubble["type"] == "bubble"
    assert bubble["hero"]["url"] == "https://example.com/photo.jpg"
    body_types = [item["type"] for item in bubble["body"]["contents"]]
    assert "button" not in body_types
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
                score=float(i),
                reasons=(),
                rank=i,
                selectable=True,
            )
            for i in range(1, 3)
        ]
    )
    bubbles = message["contents"]["contents"]
    assert len(bubbles) == 2
    assert "推薦順位 1" in bubbles[0]["body"]["contents"][0]["text"]
    button = bubbles[0]["body"]["contents"][-1]
    assert button["type"] == "button"
    assert "action=select_matched_animal" in button["action"]["data"]
    assert "hero" not in bubbles[0]
