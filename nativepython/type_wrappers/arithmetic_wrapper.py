#   Coyright 2017-2019 Nativepython Authors
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

import typed_python.python_ast as python_ast
from typed_python.type_promotion import computeArithmeticBinaryResultType

import nativepython.type_wrappers.runtime_functions as runtime_functions
from nativepython.type_wrappers.wrapper import Wrapper
from nativepython.type_wrappers.exceptions import generateThrowException
import nativepython.native_ast as native_ast
import nativepython

from typed_python import (
    Float32, Float64, Int64, Bool
)

pyOpToNative = {
    python_ast.BinaryOp.Add(): native_ast.BinaryOp.Add(),
    python_ast.BinaryOp.Sub(): native_ast.BinaryOp.Sub(),
    python_ast.BinaryOp.Mult(): native_ast.BinaryOp.Mul(),
    python_ast.BinaryOp.Div(): native_ast.BinaryOp.Div(),
    python_ast.BinaryOp.Mod(): native_ast.BinaryOp.Mod(),
    python_ast.BinaryOp.LShift(): native_ast.BinaryOp.LShift(),
    python_ast.BinaryOp.RShift(): native_ast.BinaryOp.RShift(),
    python_ast.BinaryOp.BitOr(): native_ast.BinaryOp.BitOr(),
    python_ast.BinaryOp.BitXor(): native_ast.BinaryOp.BitXor(),
    python_ast.BinaryOp.BitAnd(): native_ast.BinaryOp.BitAnd()
}

pyOpNotForFloat = {
    python_ast.BinaryOp.LShift(),
    python_ast.BinaryOp.RShift(),
    python_ast.BinaryOp.BitOr(),
    python_ast.BinaryOp.BitXor(),
    python_ast.BinaryOp.BitAnd()
}

pyCompOp = {
    python_ast.ComparisonOp.Eq(): native_ast.BinaryOp.Eq(),
    python_ast.ComparisonOp.NotEq(): native_ast.BinaryOp.NotEq(),
    python_ast.ComparisonOp.Lt(): native_ast.BinaryOp.Lt(),
    python_ast.ComparisonOp.LtE(): native_ast.BinaryOp.LtE(),
    python_ast.ComparisonOp.Gt(): native_ast.BinaryOp.Gt(),
    python_ast.ComparisonOp.GtE(): native_ast.BinaryOp.GtE()
}


class ArithmeticTypeWrapper(Wrapper):
    is_pod = True
    is_pass_by_ref = False

    def convert_default_initialize(self, context, target):
        self.convert_copy_initialize(
            context,
            target,
            nativepython.python_object_representation.pythonObjectRepresentation(context, self.typeRepresentation())
        )

    def convert_assign(self, context, target, toStore):
        assert target.isReference
        context.pushEffect(
            target.expr.store(toStore.nonref_expr)
        )

    def convert_copy_initialize(self, context, target, toStore):
        assert target.isReference
        context.pushEffect(
            target.expr.store(toStore.nonref_expr)
        )

    def convert_destroy(self, context, instance):
        pass

    def convert_unary_op(self, context, instance, op):
        if op.matches.USub:
            return context.pushPod(self, instance.nonref_expr.negate())

        return super().convert_unary_op(context, instance, op)


def toWrapper(T):
    if T is Bool:
        return BoolWrapper()
    if T.IsInteger:
        return IntWrapper(T)
    return FloatWrapper(T)


def toFloatType(T1):
    """Convert an int or float type to the enclosing float type."""
    if not T1.IsFloat:
        if T1.Bits <= 32:
            return Float32
        else:
            return Float64
    return T1


class IntWrapper(ArithmeticTypeWrapper):
    def __init__(self, T):
        super().__init__(T)

    def getNativeLayoutType(self):
        T = self.typeRepresentation

        return native_ast.Type.Int(bits=T.Bits, signed=T.IsSignedInt)

    def convert_to_type(self, context, e, target_type):
        if target_type.typeRepresentation == self.typeRepresentation:
            return e
        elif target_type.typeRepresentation in (Float64, Float32):
            return context.pushPod(
                target_type.typeRepresentation,
                native_ast.Expression.Cast(
                    left=e.nonref_expr,
                    to_type=native_ast.Type.Float(bits=target_type.typeRepresentation.Bits)
                )
            )
        elif target_type.typeRepresentation == Bool:
            return e != 0
        elif isinstance(target_type, IntWrapper):
            return context.pushPod(
                target_type.typeRepresentation,
                native_ast.Expression.Cast(
                    left=e.nonref_expr,
                    to_type=native_ast.Type.Int(
                        bits=target_type.typeRepresentation.Bits,
                        signed=target_type.typeRepresentation.IsSignedInt
                    )
                )
            )

        return super().convert_to_type(context, e, target_type)

    def convert_bin_op(self, context, left, op, right):
        if op.matches.Div:
            T = toWrapper(
                computeArithmeticBinaryResultType(
                    computeArithmeticBinaryResultType(
                        left.expr_type.typeRepresentation,
                        right.expr_type.typeRepresentation
                    ),
                    Float32
                )
            )
            return left.convert_to_type(T).convert_bin_op(op, right.convert_to_type(T))

        if right.expr_type != self:
            if isinstance(right.expr_type, ArithmeticTypeWrapper):
                promoteType = toWrapper(
                    computeArithmeticBinaryResultType(
                        self.typeRepresentation,
                        right.expr_type.typeRepresentation
                    )
                )
                return left.convert_to_type(promoteType).convert_bin_op(op, right.convert_to_type(promoteType))

            return super().convert_bin_op(context, left, op, right)

        if op.matches.Mod:
            return context.pushPod(
                int,
                native_ast.Expression.Branch(
                    cond=right.nonref_expr,
                    true=runtime_functions.mod_int64_int64.call(
                        left.toInt64().nonref_expr,
                        right.toInt64().nonref_expr
                    ),
                    false=generateThrowException(context, ZeroDivisionError())
                )
            ).convert_to_type(self)
        if op.matches.Pow:
            return left.convert_to_type(toWrapper(Float64)).convert_bin_op(
                op, right.convert_to_type(toWrapper(Float64))).convert_to_type(toWrapper(Float32))
            if left.expr_type.typeRepresentation == Int64:
                return context.pushPod(
                    self,
                    runtime_functions.pow_int64_int64.call(left.nonref_expr, right.nonref_expr)
                )
            else:
                return context.pushPod(
                    self,
                    runtime_functions.pow_int64_int64.call(left.convert_to_type(
                        toWrapper(Int64)).nonref_expr, right.convert_to_type(toWrapper(Int64)).nonref_expr)
                ).convert_to_type(self)
        if op.matches.LShift:
            return context.pushPod(
                self,
                native_ast.Expression.Branch(
                    cond=((right >= 0) & ((left == 0) | (right <= 1024))).nonref_expr,
                    true=native_ast.Expression.Binop(
                        left=left.nonref_expr,
                        right=right.nonref_expr,
                        op=pyOpToNative[op]
                    ),
                    false=generateThrowException(context, ValueError("negative shift count"))
                )
            )
        if op.matches.RShift:
            return context.pushPod(
                self,
                native_ast.Expression.Branch(
                    cond=(right >= 0).nonref_expr,
                    true=native_ast.Expression.Branch(
                        cond=(left != 0).nonref_expr,
                        true=native_ast.Expression.Binop(
                            left=left.nonref_expr,
                            right=right.nonref_expr,
                            op=pyOpToNative[op]
                        ),
                        false=native_ast.Expression.Constant(
                            val=native_ast.Constant.Int(
                                bits=max(left.expr_type.typeRepresentation.Bits,
                                         right.expr_type.typeRepresentation.Bits),
                                val=0,
                                signed=left.expr_type.typeRepresentation.IsSignedInt or
                                right.expr_type.typeRepresentation.IsSignedInt
                            )
                        )
                    ),
                    false=generateThrowException(context, ValueError("negative shift count"))
                )
            )
        if op.matches.FloorDiv:
            # this is a super-slow way of doing this because we convert to float, do the op, and back to int.
            # we should be comparing the RHS against zero and throwing our own exception.
            res = left.toFloat64()
            if res is None:
                return None
            res = res.convert_bin_op(python_ast.BinaryOp.Div(), right)
            if res is None:
                return None
            return res.toInt64()

        if op in pyOpToNative:
            return context.pushPod(
                self,
                native_ast.Expression.Binop(
                    left=left.nonref_expr,
                    right=right.nonref_expr,
                    op=pyOpToNative[op]
                )
            )
        if op in pyCompOp:
            return context.pushPod(
                bool,
                native_ast.Expression.Binop(
                    left=left.nonref_expr,
                    right=right.nonref_expr,
                    op=pyCompOp[op]
                )
            )

        # we must have a bad binary operator
        return super().convert_bin_op(context, left, op, right)


class BoolWrapper(ArithmeticTypeWrapper):
    def __init__(self):
        super().__init__(Bool)

    def getNativeLayoutType(self):
        return native_ast.Type.Int(bits=1, signed=False)

    def convert_to_type(self, context, e, target_type):
        if target_type.typeRepresentation == self.typeRepresentation:
            return e
        elif target_type.typeRepresentation in (Float64, Float32):
            return context.pushPod(
                target_type.typeRepresentation,
                native_ast.Expression.Cast(
                    left=e.nonref_expr,
                    to_type=native_ast.Type.Float(bits=target_type.typeRepresentation.Bits)
                )
            )
        elif isinstance(target_type, IntWrapper):
            return context.pushPod(
                target_type.typeRepresentation,
                native_ast.Expression.Cast(
                    left=e.nonref_expr,
                    to_type=native_ast.Type.Int(
                        bits=target_type.typeRepresentation.Bits,
                        signed=target_type.typeRepresentation.IsSignedInt
                    )
                )
            )

        return super().convert_to_type(context, e, target_type)

    def convert_unary_op(self, context, left, op):
        if op.matches.Not:
            return context.pushPod(self, left.nonref_expr.logical_not())

        return super().convert_unary_op(context, left, op)

    def convert_bin_op(self, context, left, op, right):
        if op.matches.Div:
            T = toWrapper(
                computeArithmeticBinaryResultType(
                    computeArithmeticBinaryResultType(
                        left.expr_type.typeRepresentation,
                        right.expr_type.typeRepresentation
                    ),
                    Float32
                )
            )
            return left.convert_to_type(T).convert_bin_op(op, right.convert_to_type(T))

        if right.expr_type != self:
            if isinstance(right.expr_type, ArithmeticTypeWrapper):
                promoteType = toWrapper(
                    computeArithmeticBinaryResultType(
                        self.typeRepresentation,
                        right.expr_type.typeRepresentation
                    )
                )

                return left.convert_to_type(promoteType).convert_bin_op(op, right.convert_to_type(promoteType))

            return super().convert_bin_op(context, left, op, right)

        if right.expr_type == left.expr_type:
            if op.matches.BitOr or op.matches.BitAnd or op.matches.BitXor:
                return context.pushPod(
                    self,
                    native_ast.Expression.Binop(
                        left=left.nonref_expr,
                        right=right.nonref_expr,
                        op=pyOpToNative[op]
                    )
                )

        return super().convert_bin_op(context, left, op, right)


class FloatWrapper(ArithmeticTypeWrapper):
    def __init__(self, T):
        super().__init__(T)

    def getNativeLayoutType(self):
        return native_ast.Type.Float(bits=self.typeRepresentation.Bits)

    def convert_to_type(self, context, e, target_type):
        if target_type.typeRepresentation == self.typeRepresentation:
            return e
        elif target_type.typeRepresentation in [Float32, Float64]:
            return context.pushPod(
                target_type.typeRepresentation,
                native_ast.Expression.Cast(
                    left=e.nonref_expr,
                    to_type=native_ast.Type.Float(bits=target_type.typeRepresentation.Bits)
                )
            )
        elif target_type.typeRepresentation == Int64:
            return context.pushPod(
                int,
                native_ast.Expression.Cast(
                    left=e.nonref_expr,
                    to_type=native_ast.Type.Int(bits=64, signed=True)
                )
            )
        elif target_type.typeRepresentation == Bool:
            return e != 0.0

        return super().convert_to_type(context, e, target_type)

    def convert_bin_op(self, context, left, op, right):
        if right.expr_type != self:
            if isinstance(right.expr_type, ArithmeticTypeWrapper):
                promoteType = toWrapper(
                    computeArithmeticBinaryResultType(
                        self.typeRepresentation,
                        right.expr_type.typeRepresentation
                    )
                )

                return left.convert_to_type(promoteType).convert_bin_op(op, right.convert_to_type(promoteType))

            return super().convert_bin_op(context, left, op, right)

        if op.matches.Mod:
            # TODO: might define mod_float32_float32 instead of doing these conversions
            if left.expr_type.typeRepresentation == Float32:
                return left.convert_to_type(toWrapper(Float64)).convert_bin_op(
                    op, right.convert_to_type(toWrapper(Float64))).convert_to_type(toWrapper(Float32))
            return context.pushPod(
                self,
                native_ast.Expression.Branch(
                    cond=right.nonref_expr,
                    true=runtime_functions.mod_float64_float64.call(left.nonref_expr, right.nonref_expr),
                    false=generateThrowException(context, ZeroDivisionError())
                )
            )
        if op.matches.Div:
            return context.pushPod(
                self,
                native_ast.Expression.Branch(
                    cond=right.nonref_expr,
                    true=native_ast.Expression.Binop(
                        left=left.nonref_expr,
                        right=right.nonref_expr,
                        op=pyOpToNative[op]
                    ),
                    false=generateThrowException(context, ZeroDivisionError())
                )
            )
        if op.matches.Pow:
            return context.pushPod(
                self,
                runtime_functions.pow_float64_float64.call(
                    left.nonref_expr, right.nonref_expr
                )
            )

        if op in pyOpToNative and op not in pyOpNotForFloat:
            return context.pushPod(
                self,
                native_ast.Expression.Binop(
                    left=left.nonref_expr,
                    right=right.nonref_expr,
                    op=pyOpToNative[op]
                )
            )

        if op in pyCompOp:
            return context.pushPod(
                bool,
                native_ast.Expression.Binop(
                    left=left.nonref_expr,
                    right=right.nonref_expr,
                    op=pyCompOp[op]
                )
            )

        return super().convert_bin_op(context, left, op, right)
