from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator


UploadFormat = Literal["pdf", "png", "jpeg"]
Extension = Annotated[str, StringConstraints(min_length=4, max_length=5, pattern=r"^\.[a-z]+$")]


class AllowedUploadType(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_format: UploadFormat
    extensions: list[Extension] = Field(min_length=1)
    media_type: str = Field(min_length=1, max_length=100)

    @field_validator("extensions")
    @classmethod
    def normalize_extensions(cls, values: list[str]) -> list[str]:
        return [value.lower() for value in values]

    @model_validator(mode="after")
    def validate_format_pairing(self) -> "AllowedUploadType":
        expected = {
            "pdf": ({".pdf"}, "application/pdf"),
            "png": ({".png"}, "image/png"),
            "jpeg": ({".jpg", ".jpeg"}, "image/jpeg"),
        }
        valid_extensions, valid_media_type = expected[self.file_format]
        if not set(self.extensions).issubset(valid_extensions) or self.media_type != valid_media_type:
            raise ValueError("Configured extension and media type must match the supported file format.")
        return self


class UploadPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
    max_file_size_bytes: int = Field(gt=0, le=104_857_600)
    allowed_file_types: list[AllowedUploadType] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_no_duplicate_type_mappings(self) -> "UploadPolicy":
        extensions = [extension for item in self.allowed_file_types for extension in item.extensions]
        media_types = [item.media_type for item in self.allowed_file_types]
        if len(extensions) != len(set(extensions)):
            raise ValueError("Allowed file extensions must not be duplicated.")
        if len(media_types) != len(set(media_types)):
            raise ValueError("Allowed media types must not be duplicated.")
        return self


class UploadPolicyResponse(BaseModel):
    policy: UploadPolicy
    policy_digest: str


class DocumentVersionResponse(BaseModel):
    id: str
    document_id: str
    configuration_version: str
    version_number: int
    original_filename: str
    byte_size: int
    media_type: str
    digest_algorithm: str
    sha256_digest: str
    uploaded_by: str
    upload_policy_version: str | None
    upload_policy_digest: str | None
    uploaded_at: datetime


class DocumentResponse(BaseModel):
    id: str
    institution_id: str
    fdr_record_id: str
    category_key: str
    created_by: str
    created_at: datetime
    latest_version: DocumentVersionResponse | None


class EvidenceCheckResponse(BaseModel):
    id: str
    institution_id: str
    fdr_record_id: str
    document_version_id: str | None
    check_type: str
    result_status: str
    explanation: str
    software_version: str | None
    rule_version: str | None
    evidence_references: list[str]
    result_details: dict
    human_review_decision: str | None
    executed_at: datetime


class IntegrityCheckRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
