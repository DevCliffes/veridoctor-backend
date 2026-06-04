import random
import string


def generate_code(
    length: int = 11, digits_only: bool = False, uppercase_only: bool = False
) -> str:
    """
    Generates a random string of digits
    ___
    Params:
        @length - the number of the random numbers to generate
        @digits_only - if tru returns random digits only, excludes ascii letters
    """

    if digits_only:
        characters = string.digits
    else:
        characters = string.ascii_uppercase + string.digits
    return "".join(random.choice(characters) for _ in range(length))
