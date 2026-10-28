"""All tunable settings in one place. Same seed + same size = byte-identical output."""

SEED = 20261022
START = "2026-01-01"          # first day of simulated history
DAYS = 181                    # 2026-01-01 .. 2026-06-30
YEAR = 2026                   # used in event IDs (MOV-2026-...)

# Size presets. "full" is the size the brief asks for; "small" runs the same code in seconds.
SIZES = {
    "small": dict(stores=5, skus=200, movements=20_000, counts=500, promotions=8,
                  inject=dict(wrong_store=10, missing_reason=10, count_before_movements=10,
                              transfer_double_loss=5, repeated_adjusters=2, unexplained_loss_employees=2,
                              unexplained_counts_each=5, damage_event_stores=1)),
    # half of full: easier to explore and demo, same code and the same kinds of planted cases
    "medium": dict(stores=50, skus=2_500, movements=500_000, counts=10_000, promotions=20,
                   inject=dict(wrong_store=12, missing_reason=12, count_before_movements=12,
                               transfer_double_loss=5, repeated_adjusters=3, unexplained_loss_employees=3,
                               unexplained_counts_each=6, damage_event_stores=2)),
    "full": dict(stores=100, skus=5_000, movements=1_000_000, counts=20_000, promotions=40,
                 inject=dict(wrong_store=25, missing_reason=25, count_before_movements=25,
                             transfer_double_loss=10, repeated_adjusters=4, unexplained_loss_employees=4,
                             unexplained_counts_each=6, damage_event_stores=3)),
}

ASSORTMENT_FRAC = 0.12        # each store stocks 12% of the SKU catalogue

# Baseline movement mix (share of the movement budget). Sales take whatever is left (~76%).
MIX = dict(receipts=0.10, transfer_pairs=0.03, returns=0.04, adjustments=0.03)
DAMAGED_RETURN_RATE = 0.20    # share of returns that come back unsellable and are written off
TRANSIT_LOSS_RATE = 0.02      # share of transfers lost on the way (written off once, by the receiving store)

# Staff per store, by role index (0 Cashier, 1 Stock Associate, 2 Shift Supervisor, 3 Store Manager)
STAFF = {0: 6, 1: 4, 2: 3, 3: 1}

# Planted pattern strength
REPEATED_ADJ_MULTIPLIER = 2.0   # suspect posts this many times their normal write-offs, on top of normal
UNEXPLAINED_SHORTAGE = (6, 16)  # planted count shortage, units (low inclusive, high exclusive)

# Detector thresholds (detect.py)
MASS_EVENT_MIN_ADJ = 20         # >= this many write-offs in one store-day by >= 3 people = one incident, not a pattern
REPEATED_ADJ_Z = 4.0            # Poisson z-score vs the employee's expected share of store write-offs
REPEATED_ADJ_Z_WEAK = 2.5       # ...or this z-score when write-offs are also bunched on night shifts:
NIGHT_MAX_P = 0.01              #    binomial p-value of the night share vs the role's normal night share.
                                #    Joint chance ~0.6% x 1% = 0.006% per person, as strict as z >= 4 alone (~0.003%)
BIG_SHORTAGE_UNITS = 5          # count shortage that counts as "large"
UNEXPLAINED_MIN_COUNTS = 3      # large shortages needed before blaming a person
UNEXPLAINED_MAX_P = 1e-4        # chance of seeing that many by luck must be below this
