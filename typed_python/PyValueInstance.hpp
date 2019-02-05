#pragma once

#include "PyInstance.hpp"

class PyValueInstance : public PyInstance {
public:
    typedef Value modeled_type;

    static void copyConstructFromPythonInstanceConcrete(Value* v, instance_ptr tgt, PyObject* pyRepresentation) {
        const Instance& elt = v->value();

        if (compare_to_python(elt.type(), elt.data(), pyRepresentation, false) != 0) {
            throw std::logic_error("Can't initialize a " + v->name() + " from an instance of " +
                std::string(pyRepresentation->ob_type->tp_name));
        } else {
            //it's the value we want
            return;
        }
    }

    static bool pyValCouldBeOfTypeConcrete(modeled_type* valType, PyObject* pyRepresentation) {
        if (compare_to_python(valType->value().type(), valType->value().data(), pyRepresentation, true) == 0) {
            return true;
        } else {
            return false;
        }
    }
};

