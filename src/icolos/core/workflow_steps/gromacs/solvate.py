from icolos.utils.enums.step_enums import StepGromacsEnum
from icolos.utils.enums.program_parameters import GromacsEnum
from icolos.utils.execute_external.gromacs import GromacsExecutor
from pydantic import BaseModel
from icolos.core.workflow_steps.step import _LE
from icolos.core.workflow_steps.gromacs.base import StepGromacsBase

_GE = GromacsEnum()
_SGE = StepGromacsEnum()


class StepGMXSolvate(StepGromacsBase, BaseModel):
    """
    Fill waterbox with solvent, executes gmx solvate
    """

    def __init__(self, **data):
        super().__init__(**data)

        self._initialize_backend(executor=GromacsExecutor)
        self._check_backend_availability()

    def execute(self):
        tmp_dir = self._make_tmpdir()
        self._write_input_files(tmp_dir)
        structure_file = self.data.generic.get_argument_by_extension(
            _SGE.FIELD_KEY_STRUCTURE
        )
        arguments = self._parse_arguments(
            flag_dict={
                "-cp": structure_file,
                "-p": self.data.generic.get_argument_by_extension(_SGE.FIELD_KEY_TOPOL),
                "-o": structure_file,
            }
        )
        result = self._backend_executor.execute(
            command=_GE.SOLVATE, arguments=arguments, location=tmp_dir
        )
        for line in result.stdout.split("\n"):
            self._logger_blank.log(line, _LE.DEBUG)
        self._logger.log(
            f"Completed execution for {self.step_id} successfully.", _LE.INFO
        )
        self._parse_output(tmp_dir)
        self._remove_temporary(tmp_dir)
