import taichi as ti
from pytest import approx

n = 128

def run_atomic_add_global_case(vartype, step, valproc=lambda x: x):
  x = ti.var(vartype)
  y = ti.var(vartype)
  c = ti.var(vartype)

  @ti.layout
  def place():
    ti.root.dense(ti.i, n).place(x, y)
    ti.root.place(c)

  @ti.kernel
  def func():
    ck = ti.to_numpy_type(vartype)(0)
    for i in range(n):
      x[i] = ti.atomic_add(c[None], step)
      y[i] = ti.atomic_add(ck, step)

  func()

  assert valproc(c[None]) == n * step
  x_actual = sorted(x.to_numpy())
  y_actual = sorted(y.to_numpy())
  expect = [i * step for i in range(n)]
  for (xa, ya, e) in zip(x_actual, y_actual, expect):
    assert valproc(xa) == e
    assert valproc(ya) == e


@ti.all_archs
def test_atomic_add_global_i32():
  run_atomic_add_global_case(ti.i32, 42)


@ti.all_archs
def test_atomic_add_global_f32():
  run_atomic_add_global_case(
      ti.f32, 4.2, valproc=lambda x: approx(x, rel=1e-5))


@ti.all_archs
def test_atomic_add_expr_evaled():
  c = ti.var(ti.i32)
  step = 42

  @ti.layout
  def place():
    ti.root.place(c)

  @ti.kernel
  def func():
    for i in range(n):
      # this is an expr with side effect, make sure it's not optimized out.
      ti.atomic_add(c[None], step)

  func()

  assert c[None] == n * step


@ti.all_archs
def test_atomic_add_demoted():
  # Ensure demoted atomics do not crash the program.
  x = ti.var(ti.i32)
  y = ti.var(ti.i32)
  step = 42

  @ti.layout
  def place():
    ti.root.dense(ti.i, n).place(x, y)

  @ti.kernel
  def func():
    for i in range(n):
      s = i
      # Both adds should get demoted.
      x[i] = ti.atomic_add(s, step)
      y[i] = s.atomic_add(step)

  func()

  for i in range(n):
    assert x[i] == i
    assert y[i] == i + step


@ti.all_archs
def test_atomic_add_with_local_store_simplify1():
  # Test for the following LocalStoreStmt simplification case:
  #
  # local store [$a <- ...]
  # atomic add ($a, ...)
  # local store [$a <- ...]
  #
  # Specifically, the second store should not suppress the first one, because
  # atomic_add can return value.
  x = ti.var(ti.i32)
  y = ti.var(ti.i32)
  step = 42

  @ti.layout
  def place():
    ti.root.dense(ti.i, n).place(x, y)

  @ti.kernel
  def func():
    for i in range(n):
      # do a local store
      j = i
      x[i] = ti.atomic_add(j, step)
      # do another local store, make sure the previous one is not optimized out
      j = x[i]
      y[i] = j

  func()

  for i in range(n):
    assert x[i] == i
    assert y[i] == i


@ti.all_archs
def test_atomic_add_with_local_store_simplify2():
  # Test for the following LocalStoreStmt simplification case:
  #
  # local store [$a <- ...]
  # atomic add ($a, ...)
  #
  # Specifically, the local store should not be removed, because
  # atomic_add can return its value.
  x = ti.var(ti.i32)
  step = 42

  @ti.layout
  def place():
    ti.root.dense(ti.i, n).place(x)

  @ti.kernel
  def func():
    for i in range(n):
      j = i
      x[i] = ti.atomic_add(j, step)

  func()

  for i in range(n):
    assert x[i] == i


@ti.all_archs
def test_atomic_add_with_if_simplify():
  # Make sure IfStmt simplification doesn't move stmts depending on the result
  # of atomic_add()
  x = ti.var(ti.i32)
  step = 42

  @ti.layout
  def place():
    ti.root.dense(ti.i, n).place(x)

  boundary = n / 2
  @ti.kernel
  def func():
    for i in range(n):
      if i > boundary:
        # A sequence of commands designed such that atomic_add() is the only
        # thing to decide whether the if branch can be simplified.
        s = i
        j = s.atomic_add(s)
        k = j + s
        x[i] = k
      else:
        # If we look at the IR, this branch should be simplified, since nobody
        # is using atomic_add's result.
        x[i].atomic_add(i)
        x[i] += step

  func()

  for i in range(n):
    expect = i * 3 if i > boundary else (i + step)
    assert x[i] == expect

@ti.all_archs
def test_local_atomic_with_if():
  ret = ti.var(dt=ti.i32, shape=())

  @ti.kernel
  def test():
    if True:
      x = 0
      x += 1
      ret[None] = x

  test()
  assert ret[None] == 1
