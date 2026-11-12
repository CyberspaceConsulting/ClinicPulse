from . import models


def shift_requirements(shift: models.ShiftType) -> list[models.ShiftStaffingRequirement]:
    return list(shift.staffing_requirements) or [
        models.ShiftStaffingRequirement(position=shift.position, required_staff=shift.required_staff)
    ]


def qualified_requirements(
    employee: models.Employee, shift: models.ShiftType
) -> list[models.ShiftStaffingRequirement]:
    """Requirements of the shift that the employee meets through qualifications of the shift's department."""
    names = {name.strip().casefold() for name in employee.qualification_names_for(shift.department_id)}
    return [item for item in shift_requirements(shift) if item.position.strip().casefold() in names]
