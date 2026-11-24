from pathlib import Path

from .dataset import PairedDataset, list_pairs, load_wav  # noqa: F401


def build_splits(cfg):
    """Return (train_pairs, val_pairs, test_pairs) according to ``cfg.data``."""
    d = cfg.data
    root = Path(d.root)
    tr_c, tr_n = root / d.train_clean, root / d.train_noisy
    te_c, te_n = root / d.test_clean, root / d.test_noisy
    val_spk = d.get("val_speakers") or []
    if val_spk:
        train = list_pairs(tr_c, tr_n, speakers_out=val_spk)
        val = list_pairs(tr_c, tr_n, speakers_in=val_spk)
    else:  # fall back to the test set for validation (what MP-SENet/CMGAN do)
        train = list_pairs(tr_c, tr_n)
        val = list_pairs(te_c, te_n)
    test = list_pairs(te_c, te_n)
    return train, val, test
