import unittest
import os
from icolos.core.workflow_steps.pmx.run_analysis import StepPMXRunAnalysis
from icolos.utils.enums.step_enums import StepBaseEnum
from tests.tests_paths import (
    PATHS_EXAMPLEDATA,
    create_test_dir,
    MAIN_CONFIG,
    export_unit_test_env_vars,
    get_ligands_as_compounds_with_conformers,
)
from icolos.utils.general.files_paths import attach_root_path
from icolos.core.composite_agents.workflow import WorkFlow
from icolos.core.containers.perturbation_map import PerturbationMap

_SBE = StepBaseEnum


class Test_PMXanalyse(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._test_dir = attach_root_path("tests/junk/pmx/analyse")
        #
        create_test_dir(PATHS_EXAMPLEDATA.RUN_ANALYSIS_TEST_DIR, cls._test_dir)

    def setUp(self):
        self.compounds = get_ligands_as_compounds_with_conformers(
            PATHS_EXAMPLEDATA.PMX_TNKS_LIGANDS
        )
        p_map = PerturbationMap(compounds=self.compounds)
        p_map.parse_map_file(file_path=PATHS_EXAMPLEDATA.PMX_TNKS_MAP)
        self.p_map = p_map
        self.p_map.replicas = 1
        export_unit_test_env_vars()

    def test_pmx_analyse(self):
        step_conf = {
            _SBE.STEPID: "prepare_simulations",
            _SBE.STEP_TYPE: "pmx_analyse",
            _SBE.EXEC: {
                _SBE.EXEC_PREFIXEXECUTION: "module load GROMACS/2020.3-fosscuda-2019a",
            },
            _SBE.SETTINGS: {
                _SBE.SETTINGS_ARGUMENTS: {
                    _SBE.SETTINGS_ARGUMENTS_FLAGS: [],
                    _SBE.SETTINGS_ARGUMENTS_PARAMETERS: {},
                },
                _SBE.SETTINGS_ADDITIONAL: {},
            },
        }
        step_pmx_analyse = StepPMXRunAnalysis(**step_conf)
        step_pmx_analyse.work_dir = self._test_dir
        step_pmx_analyse._workflow_object = WorkFlow()
        step_pmx_analyse._workflow_object.workflow_data.perturbation_map = self.p_map
        step_pmx_analyse.execute()

        stat_inf = os.stat(
            os.path.join(self._test_dir, "0ec09ef_4afa8f9/complex/analyse1/results.txt")
        )

        self.assertGreater(stat_inf.st_size, 19000)

        stat_inf = os.stat(os.path.join(self._test_dir, "resultsAll.csv"))

        self.assertGreater(stat_inf.st_size, 200)
