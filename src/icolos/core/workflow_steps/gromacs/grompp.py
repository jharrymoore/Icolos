from icolos.utils.enums.step_enums import StepGromacsEnum
from icolos.utils.enums.program_parameters import GromacsEnum
from icolos.core.workflow_steps.gromacs.base import StepGromacsBase
from icolos.utils.execute_external.gromacs import GromacsExecutor
from pydantic import BaseModel
from icolos.core.workflow_steps.step import _LE

_GE = GromacsEnum()
_SGE = StepGromacsEnum()


class StepGMXGrompp(StepGromacsBase, BaseModel):
    """
    Wraps gromacs preprocessor, produces tpr file preceeding mdrun step
    Automatically handles coupling group updates
    """

    def __init__(self, **data):
        super().__init__(**data)

        self._initialize_backend(executor=GromacsExecutor)
        self._check_backend_availability()

    def _auto_update_coupling_groups(self, tmp_dir):
        # this will handle most straightforward cases with protein+ligand, DNA, RNA,
        result = self._generate_index_groups(tmp_dir)
        add_other = False
        add_ions = False

        # check whether the ions and other index groups are present
        for line in result.stdout.split("\n"):
            parts = line.split()

            if len(parts) == 5:
                if parts[1] in _GE.PRIMARY_COMPONENTS:
                    primary_component = parts[1]
                    # identify Protein, DNA, RNA
                elif parts[1] == "Other":
                    add_other = True
                elif parts[1] == _SGE.WATER_AND_IONS:
                    add_ions = True

        update_dict = self._copy_fields_dict()
        pipe_input = ""
        tc_grps = ""
        if add_other:
            pipe_input += f"{primary_component} or Other"
            tc_grps += f"{primary_component}_Other"
        else:
            tc_grps += primary_component
        if add_ions:
            tc_grps += " "
            tc_grps += _SGE.WATER_AND_IONS
        else:
            tc_grps += " "
            tc_grps += "Water"

        update_dict[_SGE.TC_GRPS] = tc_grps

        if pipe_input:
            self._add_index_group(tmp_dir, pipe_input)

        # update the mdp file with the modified coupling groups
        self._modify_config_file(
            tmp_dir,
            self.data.generic.get_argument_by_extension(
                _SGE.FIELD_KEY_MDP, rtn_file_object=True
            ),
            update_dict,
        )

    def execute(self):
        """
        Set up required mdp file and run gmx grompp
        Note that any issues with your parametrisation or system building will normally cause grompp to panic
        """
        tmp_dir = self._make_tmpdir()
        self._write_input_files(tmp_dir)

        # if make_ndx command has been specified in settings.additional,
        # add an index group here, commonly protein_ligand or protein_other

        if (
            _SGE.MAKE_NDX_COMMAND in self.settings.additional.keys()
            and self.settings.additional[_SGE.MAKE_NDX_COMMAND] is not None
        ):
            # normally you want your two t-coupling groups to be something like Protein_Other Water_Ions
            # these can be added automatically with the "auto" keyword
            if self.settings.additional[_SGE.MAKE_NDX_COMMAND] == _SGE.AUTO:
                # automatically update the coupling groups, check for presence of 'ions' and 'other',
                # update default coupling groups in mdp file
                self._auto_update_coupling_groups(tmp_dir)
            else:
                # the mdp file will not be modified, coupling groups must be set correctly prior to job execution
                self._add_index_group(
                    tmp_dir, self.settings.additional[_SGE.MAKE_NDX_COMMAND]
                )

        structure_file = self.data.generic.get_argument_by_extension(
            _SGE.FIELD_KEY_STRUCTURE
        )
        mdp_file = self.data.generic.get_argument_by_extension(_SGE.FIELD_KEY_MDP)
        topol_file = self.data.generic.get_argument_by_extension(_SGE.FIELD_KEY_TOPOL)

        args = ["-r", structure_file] if self.settings.additional["-r"] else []

        arguments = self._parse_arguments(
            flag_dict={
                "-f": mdp_file,
                "-c": structure_file,
                "-p": topol_file,
                "-o": _SGE.STD_TPR,
            },
            args=args,
        )
        result = self._backend_executor.execute(
            command=_GE.GROMPP, arguments=arguments, check=True, location=tmp_dir
        )
        for line in result.stdout.split("\n"):
            self._logger_blank.log(line, _LE.DEBUG)
        self._logger.log(
            f"Completed execution for {self.step_id} successfully", _LE.INFO
        )
        self._parse_output(tmp_dir)
        self._remove_temporary(tmp_dir)
