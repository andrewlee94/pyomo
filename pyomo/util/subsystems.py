#  ___________________________________________________________________________
#
#  Pyomo: Python Optimization Modeling Objects
#  Copyright 2017 National Technology and Engineering Solutions of Sandia, LLC
#  Under the terms of Contract DE-NA0003525 with National Technology and
#  Engineering Solutions of Sandia, LLC, the U.S. Government retains certain
#  rights in this software.
#  This software is distributed under the 3-clause BSD License.
#  ___________________________________________________________________________

from pyomo.core.base.block import Block
from pyomo.core.base.reference import Reference
from pyomo.core.expr.visitor import identify_variables
from pyomo.common.collections import ComponentSet, ComponentMap


def create_subsystem_block(constraints, variables=None, include_fixed=False):
    """ This function creates a block to serve as a subsystem with the
    specified variables and constraints. To satisfy certain writers, other
    variables that appear in the constraints must be added to the block as
    well. We call these the "input vars." They may be thought of as
    parameters in the subsystem, but we do not fix them here as it is not
    obvious that this is desired.

    Arguments
    ---------
    constraints: List of Pyomo constraint data objects
    variables: List of Pyomo var data objects
    include_fixed: Bool indicating whether fixed variables should be
                   attached to the block. This is useful if they may
                   be unfixed at some point.

    Returns
    -------
    Block containing references to the specified constraints and variables,
    as well as other variables present in the constraints

    """
    if variables is None:
        variables = []
    block = Block(concrete=True)
    block.vars = Reference(variables)
    block.cons = Reference(constraints)
    var_set = ComponentSet(variables)
    input_vars = []
    for con in constraints:
        for var in identify_variables(con.body, include_fixed=include_fixed):
            if var not in var_set:
                input_vars.append(var)
                var_set.add(var)
    block.input_vars = Reference(input_vars)
    return block


class TemporarySubsystemManager(object):
    """ This class is a context manager for cases when we want to
    temporarily fix or deactivate certain variables or constraints
    in order to perform some solve or calculation with the resulting
    subsystem.

    We currently do not support fixing variables to particular values,
    and do not restore values of variables fixed. This could change.
    """

    def __init__(self, to_fix=None, to_deactivate=None, to_reset=None):
        if to_fix is None:
            to_fix = []
        if to_deactivate is None:
            to_deactivate = []
        if to_reset is None:
            to_reset = []
        self._vars_to_fix = to_fix
        self._cons_to_deactivate = to_deactivate
        self._comps_to_set = to_reset
        self._var_was_fixed = None
        self._con_was_active = None
        self._comp_original_value = None

    def __enter__(self):
        to_fix = self._vars_to_fix
        to_deactivate = self._cons_to_deactivate
        to_set = self._comps_to_set
        self._var_was_fixed = [(var, var.fixed) for var in to_fix]
        self._con_was_active = [(con, con.active) for con in to_deactivate]
        self._comp_original_value = [(comp, comp.value) for comp in to_set]

        for var in self._vars_to_fix:
            var.fix()

        for con in self._cons_to_deactivate:
            con.deactivate()

        return self

    def __exit__(self, ex_type, ex_val, ex_bt):
        for var, was_fixed in self._var_was_fixed:
            if not was_fixed:
                var.unfix()
        for con, was_active in self._con_was_active:
            if was_active:
                con.activate()
        for comp, val in self._comp_original_value:
            comp.set_value(val)


class ParamSweeper(TemporarySubsystemManager):
    """ This class enables setting values of variables/parameters
    according to a provided sequence. Iterating over this object
    sets values to the next in the sequence, at which point a
    calculation may be performed and output values compared.
    On exit, original values are restored.
    """

    def __init__(self,
            n_scenario,
            input_values,
            output_values=None,
            to_fix=None,
            to_deactivate=None,
            to_reset=None,
            ):
        """
        Parameters
        ----------
        n_scenario: The number of different values we expect for each
                    input variable
        input_values: ComponentMap mapping each input variable to a list
                      of values of length n_scenario
        output_values: ComponentMap mapping each output variable to a list
                       of values of length n_scenario
        """
        # Should this object be aware of the user's block/model?
        # My answer for now is no.
        self.input_values = input_values
        self.output_values = output_values if output_values is not None else {}
        self.n_scenario = n_scenario
        self.initial_state_values = None
        self._ip = -1 # Index pointer for iteration

        if to_reset is None:
            to_reset = [var for var in input_values]
        else:
            to_reset.extend(var for var in input_values)

        super(ParamSweeper, self).__init__(
                to_fix=to_fix,
                to_deactivate=to_deactivate,
                to_reset=to_reset,
                )

    def __iter__(self):
        return self

    def __next__(self):
        self._ip += 1

        i = self._ip
        n_scenario = self.n_scenario
        input_values = self.input_values
        output_values = self.output_values

        if i >= n_scenario:
            self._ip = -1
            raise StopIteration()

        else:
            inputs = ComponentMap()
            for var, values in input_values.items():
                val = values[i]
                var.set_value(val)
                inputs[var] = val

            outputs = ComponentMap([
                (var, values[i]) for var, values in output_values.items()
                ])

            return inputs, outputs
