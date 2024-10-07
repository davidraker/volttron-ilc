import numpy as np

from ilc.fucom import fucom

# TODO: This code runs the scenarios from the FUCOM paper. Make them into a test.
print('\n\n====================================================\n\n')
print('example 1')
obj = [1, 0, 0, 0, 0]
lhs_ineq = np.array([[-1.08, 1., -1.08, 0., 0.],
            [-1.25, 0., 1., -1.25, 0.],
            [-1.45, 0., 0., 1., -1.45],
            [-135., 1., 0., -1.35, 0.],
            [-1.81, 0., 1., 0., -1.81],
            ])
rhs_ineq = [0, 0, 0, 0, 0]
lhs_eq = [[0, 1, 1, 1, 1]]
rhs_eq = [1]
bnd = [(0, float('inf')), (0, 1), (0, 1), (0, 1), (0, 1)]
opt = linprog(c=obj, A_ub=lhs_ineq, b_ub=rhs_ineq, A_eq=lhs_eq, b_eq=rhs_eq, bounds=bnd,
              method='revised simplex')
print("lhs_ineq")
print(lhs_ineq)
print("rhs_ineq")
print(rhs_ineq)
print("lhs_eq")
print(lhs_eq)
print("rhs_eq")
print(rhs_eq)
print("bounds")
print(bnd)
print(opt.x)
print('\n---------------------------------------------------\n')
print('fucom example 1')
do1 = {}
fucom_result1 = fucom({'c1': 1, 'c2': 1.08, 'c3': 1.35, 'c4': 1.9575}, out_debug_dict=do1)
for k, v in do1.items():
    print(f'k: ')
    print(v)
print(fucom_result1)
print('\n\n==================================================\n\n')
print('example 2')
obj2 = [1, 0, 0, 0, 0, 0]
lhs_ineq2 = np.array([[-1.0,    1.0,    -2.1,   0.0,    0.0,    0.0],
                      [-1.0,   0.0,    1.0,    -1.43,  0.0,    0.0],
                      [-1.0,    0.0,    0.0,    1.0,   -1.0,    0.0],
                      [-1.0,   0.0,    0.0,    0.0,    1.0,    -2.33],
                      [-1.0,    1.0,    0.0,    -3.0,   0.0,    0.0],
                      [-1.0,   0.0,    1.0,    0.0,    -1.43,  0.0],
                      [-1.0,   0.0,    0.0,    1.0,    0.0,    -2.33333333]
                      ])
rhs_ineq2 = [0, 0, 0, 0, 0, 0, 0]
lhs_eq2 = [[0, 1, 1, 1, 1, 1]]
rhs_eq2 = [1]
bnd2 = [(0, float('inf')), (0, 1), (0, 1), (0, 1), (0, 1), (0, 1)]
opt2 = linprog(c=obj2, A_ub=lhs_ineq2, b_ub=rhs_ineq2, A_eq=lhs_eq2, b_eq=rhs_eq2, bounds=bnd2,
              method='revised simplex')
print("lhs_ineq")
print(lhs_ineq2)
print("rhs_ineq")
print(rhs_ineq2)
print("lhs_eq")
print(lhs_eq2)
print("rhs_eq")
print(rhs_eq2)
print("bounds")
print(bnd2)
print(opt2.x)
print('\n---------------------------------------------------\n')
print('fucom example 2')
do2 = {}
fucom_result2 = fucom({'c2': 1, 'c1': 2.1, 'c4': 3, 'c3': 3, 'c5': 7}, out_debug_dict=do2)
for k, v in do2.items():
    print(f'{k}: ')
    print(v)
print(fucom_result2)
print('==================================================')
