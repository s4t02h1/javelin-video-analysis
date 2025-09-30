def apply_ema(data, alpha=0.1):
    """Apply Exponential Moving Average (EMA) filter to smooth data."""
    ema_data = []
    for i, value in enumerate(data):
        if i == 0:
            ema_data.append(value)
        else:
            ema_data.append(alpha * value + (1 - alpha) * ema_data[-1])
    return ema_data

def apply_median_filter(data, kernel_size=3):
    """Apply a median filter to smooth data."""
    from scipy.signal import medfilt
    return medfilt(data, kernel_size)