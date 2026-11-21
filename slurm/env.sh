# Edit for your cluster. Sourced by every sbatch script.
# Option A: conda
#   module load anaconda3 && conda activate se-ablation
# Option B: venv
#   module load python/3.10 cuda/12.1 && source .venv/bin/activate
if [[ -f .venv/bin/activate ]]; then source .venv/bin/activate; fi
export PYTHONUNBUFFERED=1
export OMP_NUM_THREADS=${SLURM_CPUS_PER_TASK:-8}
