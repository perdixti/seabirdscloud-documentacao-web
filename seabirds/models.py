from pydantic import BaseModel, ConfigDict, Field, field_validator


class RenderOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    links: bool = True
    tables: bool = True
    table_cards: bool = True
    code_cards: bool = True
    copy_buttons: bool = True
    raw_html: bool = True


class ImageAttachment(BaseModel):
    id: str = Field(pattern=r"^[a-f0-9]{32}$")
    path: str = Field(max_length=4096)
    filename: str = Field(max_length=255)
    web_path: str = Field(max_length=4096)


class GenerationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    template_path: str = Field(default="", max_length=4096)
    output_path: str = Field(default="", max_length=4096)
    images_dir: str = Field(default="", max_length=4096)
    image_web_path: str = Field(default="imagens", max_length=4096)
    image_index: int = Field(default=0, ge=0, le=1_000_000)
    site_dir: str = Field(default="", max_length=4096)
    github_repository_path: str = Field(default="", max_length=4096)
    history_interval: int = Field(default=60, ge=1, le=86400)
    history_limit: int = Field(default=10, ge=1, le=1000)
    images: list[ImageAttachment] = Field(default_factory=list, max_length=1000)
    catalog_category: str = Field(default="", max_length=100)
    catalog_description: str = Field(default="", max_length=2000)
    catalog_image: str = Field(default="", max_length=4096)
    register_catalog: bool = False
    save_source: bool = False
    output_version: str = Field(default="", pattern=r"^(?:[a-f0-9]{64})?$")
    review_mode: str = Field(default="suggest", pattern=r"^(off|suggest|auto|auto-all)$")


class DocumentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(default="Sem título", min_length=1, max_length=200)
    markdown: str = Field(default="", max_length=1_000_000)
    template: str = Field(default="", max_length=1_000_000)
    options: RenderOptions = Field(default_factory=RenderOptions)
    version: int = Field(default=0, ge=0)
    generation: GenerationSettings = Field(default_factory=GenerationSettings)

    @field_validator("title")
    @classmethod
    def clean_title(cls, value: str) -> str:
        return value.strip() or "Sem título"

    @field_validator("template")
    @classmethod
    def check_template(cls, value: str) -> str:
        if value and "{{content}}" not in value:
            raise ValueError("O template precisa conter {{content}}.")
        return value
