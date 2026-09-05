"""Resume schema definition."""
from typing import List, Optional, Union
from pydantic import BaseModel, Field


class EducationItem(BaseModel):
    """An educational degree or qualification entry."""
    institution: str = Field(..., description="Name of the school, college, or university")
    degree: str = Field(..., description="Degree or program completed, e.g. B.S. Computer Science")
    year: Optional[Union[int, str]] = Field(None, description="Graduation year or date range, e.g. 2022")


class ExperienceItem(BaseModel):
    """A professional employment or work experience entry."""
    company: str = Field(..., description="Employer or organization name")
    title: str = Field(..., description="Job title or role held")
    duration: str = Field(..., description="Duration or time range of employment, e.g. '2020 - 2023'")


class ResumeData(BaseModel):
    """Structured fields extracted from a resume or CV document."""
    name: str = Field(..., description="Full name of the candidate")
    email: str = Field(..., description="Primary contact email address")
    phone: str = Field(..., description="Phone or contact number")
    skills: List[str] = Field(
        default_factory=list,
        description="List of technical, analytical, or domain skills"
    )
    education: List[EducationItem] = Field(
        default_factory=list,
        description="Educational background records"
    )
    experience: List[ExperienceItem] = Field(
        default_factory=list,
        description="Work experience records"
    )
