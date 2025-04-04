from importlib.resources import path
from subprocess import CompletedProcess
from typing import Dict, List
from icolos.core.containers.perturbation_map import Edge
from icolos.core.workflow_steps.pmx.base import StepPMXBase
from pydantic import BaseModel
from icolos.core.workflow_steps.step import _LE
import numpy as np
from icolos.utils.enums.program_parameters import (
    SlurmEnum,
    StepPMXEnum,
)
from icolos.utils.execute_external.batch_executor import BatchExecutor
from icolos.utils.execute_external.gromacs import GromacsExecutor
from icolos.utils.general.parallelization import SubtaskContainer
import os

_SE = SlurmEnum()
_PSE = StepPMXEnum()


class StepPMXRunSimulations(StepPMXBase, BaseModel):
    """
    Runs md simulations, unwraps into pool of individual jobs, parallelized over available GPUs
    """

    sim_type: str = ""

    def __init__(self, **data):
        super().__init__(**data)

        # Note: if youre running the job on, for example, a workstation, without slurm, this will simply execute the scripts directly (the slurm header is simply ignored in this case)
        self._initialize_backend(executor=BatchExecutor)

    def execute(self):

        if self.run_type == "rbfe":
            edges = [e.get_edge_id() for e in self.get_edges()]
        elif self.run_type == "abfe":
            edges = [c.get_index_string() for c in self.get_compounds()]
        self.sim_type = self.settings.additional[_PSE.SIM_TYPE]
        assert (
            self.sim_type in self.mdp_prefixes.keys()
        ), f"sim type {self.sim_type} not recognised!"

        # prepare and pool jobscripts, unroll replicas, states etc
        job_pool = self._prepare_job_pool(edges)
        self._logger.log(
            f"Prepared {len(job_pool)} jobs for {self.sim_type} simulations", _LE.DEBUG
        )
        # run everything through in one batch, with multiple edges per call
        self.execution.parallelization.max_length_sublists = int(
            np.ceil(len(job_pool) / self._get_number_cores())
        )
        self._subtask_container = SubtaskContainer(
            max_tries=self.execution.failure_policy.n_tries
        )
        self._subtask_container.load_data(job_pool)
        self._execute_pmx_step_parallel(
            run_func=self._execute_command, step_id="pmx_run_simulations"
        )

    def get_mdrun_command(
        self,
        tpr=None,
        ener=None,
        confout=None,
        mdlog=None,
        trr=None,
    ):

        # EM
        if self.sim_type in ("em", "eq", "npt", "nvt"):
            job_command = [
                "gmx",
                "mdrun",
                "-s",
                tpr,
                "-e",
                ener,
                "-c",
                confout,
                "-o",
                trr,
                "-g",
                mdlog,
            ]
            for flag in self.settings.arguments.flags:
                job_command.append(flag)
            for key, value in self.settings.arguments.parameters.items():
                job_command.append(key)
                job_command.append(value)

        elif self.sim_type == "transitions":
            # need to add many job commands to the slurm file, one for each transition
            job_command = []
            for i in range(1, 81):
                single_command = [
                    "gmx",
                    "mdrun",
                    "-s",
                    f"ti{i}.tpr",
                    "-e",
                    ener,
                    "-c",
                    confout,
                    "-dhdl",
                    f"dhdl{i}.xvg",
                    "-o",
                    trr,
                    "-g",
                    mdlog,
                    "-pme",
                    "gpu",
                ]
                for flag in self.settings.arguments.flags:
                    single_command.append(flag)
                for key, value in self.settings.arguments.parameters.items():
                    single_command.append(key)
                    single_command.append(value)
                single_command.append("\n\n")
                job_command += single_command

        return job_command

    def _prepare_single_job(self, edge: str, wp: str, state: str, r: int):
        """
        Construct a slurm job file in that job's directory, return the path to the batch script
        """
        simpath = self._get_specific_path(
            workPath=self.work_dir,
            edge=edge,
            wp=wp,
            state=state,
            r=r,
            sim=self.sim_type,
        )
        tpr = "{0}/tpr.tpr".format(simpath)
        ener = "{0}/ener.edr".format(simpath)
        confout = "{0}/confout.gro".format(simpath)
        mdlog = "{0}/md.log".format(simpath)
        trr = "{0}/traj.trr".format(simpath)
        try:
            with open(os.path.join(simpath, "md.log"), "r") as f:
                lines = f.readlines()
            sim_complete = any(["Finished mdrun" in l for l in lines])
        except FileNotFoundError:
            sim_complete = False
        if not sim_complete:
            self._logger.log(
                f"Preparing: {wp} {edge} {state} run{r}, simType {self.sim_type}",
                _LE.DEBUG,
            )
            job_command = self.get_mdrun_command(
                tpr=tpr,
                trr=trr,
                ener=ener,
                confout=confout,
                mdlog=mdlog,
            )
            job_command = " ".join(job_command)
            batch_file = self._backend_executor.prepare_batch_script(
                job_command, arguments=[], location=simpath
            )
            return os.path.join(simpath, batch_file)

        return

    def _prepare_job_pool(self, edges: List[str]):
        replicas = (
            self.get_perturbation_map().replicas
            if self.get_perturbation_map() is not None
            else 1
        )
        batch_script_paths = []
        for edge in edges:
            for state in self.states:
                for r in range(1, replicas + 1):
                    for wp in self.therm_cycle_branches:
                        path = self._prepare_single_job(
                            edge=edge, wp=wp, state=state, r=r
                        )
                        if path is not None:
                            batch_script_paths.append(path)
        return batch_script_paths

    def _execute_command(self, jobs: List[str]):
        """
        Execute the simulations for a batch of edges
        """
        for idx, job in enumerate(jobs):
            self._logger.log(
                f"Starting execution of job {job.split('/')[-1]}. ",
                _LE.DEBUG,
            )
            self._logger.log(f"Batch progress: {idx+1}/{len(jobs)}", _LE.DEBUG)
            location = "/".join(job.split("/")[:-1])
            self._backend_executor.execute(tmpfile=job, location=location, check=False)

    # def _inspect_log_files()
