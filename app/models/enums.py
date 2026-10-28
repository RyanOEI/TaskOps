import enum


class RoleEnum(str, enum.Enum):
    ADMIN = "ADMIN"
    STAFF = "STAFF"


class TaskStatus(str, enum.Enum):
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    PENDING = "PENDING"
    WAITING_REVIEW = "WAITING_REVIEW"
    COMPLETED = "COMPLETED"


class TaskPriority(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


class ItemStatus(str, enum.Enum):
    REQUESTED = "REQUESTED"
    ORDERED = "ORDERED"
    SHIPPED = "SHIPPED"
    RECEIVED = "RECEIVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"

