#tracking/validation/trust_score.py
def compute_trust_score(speed_violation, teleport, fake_pattern):
    score = 100

    if speed_violation:
        score -= 40

    if teleport:
        score -= 60

    if fake_pattern:
        score -= 30

    return max(score, 0)