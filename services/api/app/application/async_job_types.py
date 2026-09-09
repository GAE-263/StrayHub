"""Explicit ownership of persisted jobs during the Celery migration."""

LEGACY_POLLING_JOB_TYPES: frozenset[str] = frozenset()
CELERY_JOB_TYPES = frozenset(
    {
        "care_observation",
        "care_report_summary",
        "adoption_suitability",
        "adoption_profile_extraction",
        "adoption_followup_recommendations",
        "adoption_recommendation_curation",
        "growth_diary_analysis",
    }
)

CELERY_TASK_BY_JOB_TYPE = {
    "care_observation": "care_report.process_ai",
    "care_report_summary": "care_report.process_ai",
    "adoption_suitability": "adoption.analyze_suitability",
    "adoption_profile_extraction": "adoption.extract_profile",
    "adoption_followup_recommendations": "adoption.generate_followups",
    "adoption_recommendation_curation": "adoption.curate_recommendations",
    "growth_diary_analysis": "growth_diary.analyze_entry",
}
