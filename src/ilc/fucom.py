import numpy as np

from collections import OrderedDict
from scipy.optimize import linprog


def fucom(ranked_criteria: dict[str, float], out_debug_dict=None) -> dict[str: float]:
    """
    Takes a dictionary of ranked criteria and returns a dictionary with the optimal weights of these same criteria.
        Criteria should be ranked on a scale from 1 to 10, relative to the most significant criterion.
        Lower numbers represent greater significance than higher numbers.
        The most significant criterion should be ranked 1.

        An optional argument, out_debug_dict can be used as an output parameter to inspect the input used to linprog
          within the function. Pass an empty dictionary to out_debug_dict, and it will contain the parameters passed
          to linprog() once these are available (before linprog has run).
    """
    sorted_criteria = OrderedDict(sorted(ranked_criteria.items(), key=lambda item: item[1]))
    criteria_count = len(sorted_criteria)
    objective = [1] + [0]*criteria_count
    lhs_ineq = np.zeros([2*criteria_count-3, criteria_count+1])
    lhs_ineq[:,0] = -1  # First column represents the minimized variable.
    criteria_values = list(sorted_criteria.values())
    for c in range(criteria_count-1):
        lhs_ineq[c, c+1] = 1
        lhs_ineq[c, c+2] = -criteria_values[c+1] / criteria_values[c]
    for c in range(criteria_count-2):
        lhs_ineq[c+criteria_count-1, c+1] = 1
        lhs_ineq[c+criteria_count-1, c+3] = -criteria_values[c+2]/criteria_values[c]
    rhs_ineq = np.zeros([1, lhs_ineq.shape[0]])
    lhs_eq = [[0] + [1]*criteria_count]
    rhs_eq = [1]
    bounds = [(0, float('inf'))] + [(0, 1)]*criteria_count
    if isinstance(out_debug_dict, dict):
        # Debug parameters is not returned, but is available to the caller if a dict was passed in.
        out_debug_dict.update({"objective": objective, "lhs_ineq": lhs_ineq, "rhs_ineq": rhs_ineq,
                            "lhs_eq": lhs_eq, "rhs_eq": rhs_eq, "bounds": bounds})
    result = linprog(c=objective, A_ub=lhs_ineq, b_ub=rhs_ineq, A_eq=lhs_eq, b_eq=rhs_eq,
                     bounds=bounds, method='revised simplex')
    criteria_weights = {k: result.x[i+1] for i, k in enumerate(sorted_criteria.keys())}
    return criteria_weights
