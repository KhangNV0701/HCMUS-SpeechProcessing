# Sourced by every sbatch script. Edit for your cluster.
# Activates, in order of preference: ./.venv, else the conda env $CONDA_ENV (default: hcmus-sh).
#   Use another env:  CONDA_ENV=myenv sbatch slurm/train.sbatch
# Add any `module load cuda/... gcc/...` lines your cluster needs here.
CONDA_ENV=${CONDA_ENV:-hcmus-sh}

if [[ -f .venv/bin/activate ]]; then
    source .venv/bin/activate
else
    # `conda activate` needs the shell hook in non-interactive batch shells.
    if ! command -v conda >/dev/null 2>&1 && [[ -f /share/apps/ngs-ccts/miniconda/etc/profile.d/conda.sh ]]; then
        source /share/apps/ngs-ccts/miniconda/etc/profile.d/conda.sh
    fi
    if command -v conda >/dev/null 2>&1; then
        eval "$(conda shell.bash hook)"
        conda activate "$CONDA_ENV"
    fi
fi

echo "python: $(command -v python) ($(python --version 2>&1))"
export PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK:-8}
