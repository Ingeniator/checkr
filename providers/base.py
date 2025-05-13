from abc import ABC, abstractmethod
from schemas.validators import ValidatorDetail

class BaseValidatorProvider(ABC):
    source_prefix: str = ""

    @abstractmethod
    async def fetch_frontend_validators(self) -> list[ValidatorDetail]:
        """
        Fetches frontend validators from some provider (ex. gitlab/github/external service)
        
        Returns:
            list[ValidatorDetail]: Info about available frontend validators
        """
        pass
    
    async def fetch_frontend_validator_source(self, file_path: str) -> str:
        """
        Fetches the raw content of a validator source file given its path in the repository.

        Args:
            file_path (str): The path to the file in the GitLab repo.

        Returns:
            str: The content of the file as a UTF-8 decoded string, or an empty string if error occurs.
        """
        pass
    
    async def fetch_frontend_base_validators_source(self) -> dict[str, str]:
        """
        Fetches the raw content of a base validator source files given its path in the repository.


        Returns:
            dict[source, content]: Dict with the content of the files as a UTF-8 decoded string, or an empty dict if error occurs.
        """
        pass
        