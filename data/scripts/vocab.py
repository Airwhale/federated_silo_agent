"""In-repo vocabulary map for the conditions / drugs / measurements
we care about in the demo.

The AWS Synthea-OMOP datasets don't include OMOP vocabulary tables
(concept, concept_relationship, concept_ancestor). Rather than pull a
full vocabulary download (~hundreds of MB), we hand-curate a small
concept map covering only what the demo needs.

OMOP concept_ids are the standardized internal IDs; SNOMED / LOINC /
RxNorm codes are the source codes Synthea actually emits as
condition_source_value / measurement_source_value / drug_source_value.

References:
  - OMOP CDM v5.4: https://ohdsi.github.io/CommonDataModel/cdm54.html
  - SNOMED CT browser: https://browser.ihtsdotools.org/
  - OHDSI Athena (concept lookup): https://athena.ohdsi.org/
"""

from __future__ import annotations


# === CONDITIONS ===
# Format: friendly_name -> {snomed_codes, omop_concept_ids}

CONDITIONS = {
    # Heart failure family — we will synthetically inject these into a
    # subset of cardiac patients because Synthea's small populations
    # don't always generate them naturally.
    "heart_failure": {
        "snomed_codes": ["84114007", "42343007", "10633002"],
        "primary_snomed": "84114007",
        "primary_omop_concept_id": 316139,  # Heart failure (OMOP)
        "description": "Heart failure",
    },
    # Cardiac amyloidosis — even rarer; synthetic injection in scenarios.
    "amyloid_cardiomyopathy": {
        "snomed_codes": ["17552002"],
        "primary_snomed": "17552002",
        "primary_omop_concept_id": 4329701,  # Amyloid cardiomyopathy
        "description": "Cardiac amyloidosis",
    },
    # Conditions that ARE present in the 1k Synthea dataset
    "coronary_arteriosclerosis": {
        "snomed_codes": ["53741008"],
        "primary_omop_concept_id": 317576,
        "description": "Coronary arteriosclerosis (CAD)",
    },
    "atrial_fibrillation": {
        "snomed_codes": ["49436004"],
        "primary_omop_concept_id": 313217,
        "description": "Atrial fibrillation",
    },
    "myocardial_infarction": {
        "snomed_codes": ["22298006", "57054005"],
        "primary_omop_concept_id": 4329847,
        "description": "Myocardial infarction",
    },
    "hypertensive_disorder": {
        "snomed_codes": ["38341003", "59621000"],
        "primary_omop_concept_id": 316866,
        "description": "Essential hypertension",
    },
    # Comorbidities
    "type2_diabetes": {
        "snomed_codes": ["44054006"],  # Diabetes mellitus type 2
        "primary_omop_concept_id": 201826,
        "description": "Type 2 diabetes mellitus",
    },
    "chronic_kidney_disease": {
        "snomed_codes": ["431855005", "431857002", "433144002"],  # CKD stages
        "primary_omop_concept_id": 443611,
        "description": "Chronic kidney disease",
    },
}


# Cardiac-condition concept_ids (used to filter the patient pool)
CARDIAC_OMOP_CONCEPT_IDS = [
    316139,    # Heart failure (we inject this)
    4329701,   # Amyloid cardiomyopathy (we inject this)
    317576,    # Coronary arteriosclerosis
    313217,    # Atrial fibrillation
    4329847,   # Myocardial infarction
    316866,    # Essential hypertension
]

CHF_OMOP_CONCEPT_IDS = [316139, 4329701]


# === MEASUREMENTS / LABS ===
# LOINC codes that Synthea actually emits in measurement.measurement_source_value

MEASUREMENTS = {
    "body_mass_index": {
        "loinc_codes": ["39156-5"],
        "primary_omop_concept_id": 3038553,
        "description": "Body mass index",
        "typical_range": (10, 80),
    },
    "ejection_fraction": {
        "loinc_codes": ["10230-1", "8806-2", "18043-0"],
        "primary_omop_concept_id": 3027018,
        "description": "Left ventricular ejection fraction",
        "typical_range": (5, 80),
    },
    "systolic_bp": {
        "loinc_codes": ["8480-6"],
        "primary_omop_concept_id": 3004249,
        "description": "Systolic blood pressure",
        "typical_range": (60, 250),
    },
    "diastolic_bp": {
        "loinc_codes": ["8462-4"],
        "primary_omop_concept_id": 3012888,
        "description": "Diastolic blood pressure",
        "typical_range": (30, 150),
    },
    "hemoglobin_a1c": {
        "loinc_codes": ["4548-4"],
        "primary_omop_concept_id": 3004410,
        "description": "Hemoglobin A1c",
        "typical_range": (4, 18),
    },
    "creatinine": {
        "loinc_codes": ["2160-0"],
        "primary_omop_concept_id": 3016723,
        "description": "Serum creatinine",
        "typical_range": (0.3, 15),
    },
}


# === DRUGS ===
# RxNorm ingredient concept_ids for GDMT (guideline-directed medical therapy) for HF

DRUG_INGREDIENTS = {
    "ace_inhibitors": {
        "rxnorm_codes": ["1808"],  # lisinopril
        "omop_concept_ids": [1308216, 1308842, 1310756],
        "description": "ACE inhibitors (lisinopril, enalapril, ramipril)",
    },
    "arbs": {
        "rxnorm_codes": ["52175"],  # losartan
        "omop_concept_ids": [1367500, 1308257, 974166],
        "description": "Angiotensin receptor blockers (losartan, valsartan)",
    },
    "beta_blockers": {
        "rxnorm_codes": ["20352"],  # carvedilol
        "omop_concept_ids": [1346823, 1307046, 1338005],
        "description": "Beta blockers (carvedilol, metoprolol, bisoprolol)",
    },
    "loop_diuretics": {
        "rxnorm_codes": ["4603"],  # furosemide
        "omop_concept_ids": [956874, 970250],
        "description": "Loop / aldosterone diuretics (furosemide, spironolactone)",
    },
}

# Note: these OMOP concept_ids are best-guess from common ATHENA lookups.
# Where the dataset uses different ingredient concept_ids, our GDMT
# adherence check will under-count. For the demo we'll also accept
# drug_source_value text-match on common HF drug names as a fallback —
# see feature_engineering.py.
