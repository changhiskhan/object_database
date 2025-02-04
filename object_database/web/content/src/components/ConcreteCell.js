/**
 * Base class for all 'ConcreteCell' objects, which are Cells. with a
   fixed set of children. Children can expect that 'renderChildNamed'
   exists and just need to override 'build'.

   The expectation is that 'props' never change, so this dom element
   is stable.
 */

import {Cell, copyNodeInto, makeDomElt} from './Cell';

class ConcreteCell extends Cell {
    constructor(props, ...args){
        super(props, ...args);

        // Bind context to methods
        this.build = this.build.bind(this);
        this.renderChildNamed = this.renderChildNamed.bind(this);
        this.renderChildArray = this.renderChildArray.bind(this);

        // this should never be set more than once
        this.domElement = null;

        // cache our fill space preferences, so that it doesnt
        // jam the tree when we go up and down
        this._fillSpacePrefs = null;

        // maps from 'child name', which is either the name of the child
        // or (name + "#" + i) where 'i' is the index of the child in a
        // named child list. This lets us update children when they recompute
        // without having to remember where we got the rendered child.
        this.childNameToChild = {};
        this.childNameToDomElt = {};
        this.cellIdToChildName = {};
    }

    childChanged(child) {
        if (this.domElement === null) {
            return;
        }

        let childName = this.cellIdToChildName[child.identity];

        if (childName === null) {
            return;
        }

        function isDescendant(parent, child) {
             var node = child.parentNode;
             while (node != null) {
                 if (node == parent) {
                     return true;
                 }
                 node = node.parentNode;
             }
             return false;
        }

        let newChildDomElement = this.renderChildUncached(
            this.childNameToChild[childName]
        );

        // insist that our dom element is a parent of this one
        // we only need to turn this on if we see cases where cells are making multiple
        // copies of themselves and the replacement mechanism is not working.

        // if (!isDescendant(this.domElement, this.childNameToDomElt[childName])) {
        //     throw new Error("Somehow this child is not in our dom!");
        // }

        this.childNameToDomElt[childName].replaceWith(
            newChildDomElement
        );

        this.childNameToDomElt[childName] = newChildDomElement;

        this.childSpacePreferencesChanged(child);
    }

    // our 'data' has changed, which may include the set of named children, so we have
    // to rebuild the domElement. Because our parents actually track exactly what dom element
    // we return, and its not allowed to become a new one, we have to build and then replace
    rebuildDomElement() {
        this.childNameToChild = {};
        this.childNameToDomElt = {};
        this.cellIdToChildName = {};

        let newDomElt = this.build();

        this.applySpacePreferencesToClassList(newDomElt);

        copyNodeInto(newDomElt, this.domElement);
    }

    // subclasses should implement this so that it returns
    // a dom element and uses 'renderChildNamed' and 'renderChildrenNamed'.
    // note that when a concrete cell is rebuilt, we don't actually replace the domElement,
    // but rather, we call 'build' and replace the children and properties of 'domElement'
    // with what we get out of build.
    build() {
        throw new Error('build not defined for ' + this);
    }

    buildDomElementInner() {
        if (this.domElement === null) {
            this.domElement = this.build();
        }

        this.applySpacePreferencesToClassList(this.domElement);

        return this.domElement;
    }

    renderChildrenNamed(name) {
        let child = this.namedChildren[name];

        if (!child) {
            return null;
        }

        return this.renderChildArray(child, "");
    }

    onOwnSpacePrefsChanged() {
        this.applySpacePreferencesToClassList(this.domElement);
    }

    // recompute our space preferences and send up the tree
    childSpacePreferencesChanged(child) {
        let newSpacePreferences = this._computeFillSpacePreferences();

        if (newSpacePreferences.horizontal != this._fillSpacePrefs.horizontal ||
                newSpacePreferences.vertical != this._fillSpacePrefs.vertical) {

            console.log(
                "Cell " + this + "(" + this.identity + ") changed prefs from "
                + JSON.stringify(this._fillSpacePrefs)
                + " to " + JSON.stringify(newSpacePreferences)
            )

            this._fillSpacePrefs = newSpacePreferences;
            this.parent.childSpacePreferencesChanged(this);
            this.onOwnSpacePrefsChanged();
        }
    }

    // check our cache
    getFillSpacePreferences() {
        if (!this._fillSpacePrefs) {
            this._fillSpacePrefs = this._computeFillSpacePreferences();
        }

        return this._fillSpacePrefs;
    }

    renderChildArray(childOrArray, suffix) {
        if (Array.isArray(childOrArray)) {
            // this is an array of children or other arrays
            let children = [];

            for (var i = 0; i < childOrArray.length; i += 1) {
                children.push(this.renderChildArray(childOrArray[i], suffix + "#" + i));
            }

            return children;
        } else {
            // this is a concrete child
            this.cellIdToChildName[childOrArray.identity] = name + suffix;
            this.childNameToDomElt[name + suffix] = this.renderChildUncached(childOrArray);
            this.childNameToChild[name + suffix] = childOrArray;

            return this.childNameToDomElt[name + suffix];
        }
    }

    renderChildNamed(name) {
        let child = this.namedChildren[name];

        if (!child) {
            return null;
        }

        this.childNameToChild[name] = child;
        this.cellIdToChildName[child.identity] = name;
        this.childNameToDomElt[name] = this.renderChildUncached(child);

        return this.childNameToDomElt[name];
    }

    // render a child, but if it doesn't return a div,
    // return a 'displayless' div we can use as a placeholder
    // so that if the cell then _does_ render in the future,
    // we know where in the tree to put the div.
    renderChildUncached(child) {
        let div = child.buildDomElement();

        if (div === null) {
            return makeDomElt('div', {
                'style': 'display:none;'
            }, []);
        }

        return div;
    }
}

export {ConcreteCell, ConcreteCell as default};
