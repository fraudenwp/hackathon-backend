from typing import List, Optional


def get_string_array_params(string: Optional[str] = None) -> List[str]:
    return (
        [param.strip() for param in string.split(",") if param.strip()]
        if string
        else []
    )
