#target illustrator

(function () {
    var CANVAS_WIDTH = 446;
    var CANVAS_HEIGHT = 910;
    var scriptFile = new File($.fileName);
    var repoFolder = scriptFile.parent.parent;
    var sourceFile = new File(repoFolder.fsName + "/Pikita V4.ai");
    var outputFolder = new Folder(repoFolder.fsName + "/assets/rig/sublayers");
    var oldInteractionLevel = app.userInteractionLevel;
    var workingCopy = new File(Folder.temp.fsName + "/pikita-export-" + (new Date().getTime()) + ".ai");
    var doc = null;
    var allLayers = [];
    var allPageItems = [];
    var visibleGroups = [];
    var visibleObjects = [];
    var exportEntries = [];
    var groupEntries = [];
    var objectEntries = [];
    var bounds = [Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY,
                  Number.NEGATIVE_INFINITY, Number.POSITIVE_INFINITY];

    function ensureFolder(folder) {
        if (folder.exists) return;
        if (!folder.create()) throw new Error("Could not create folder: " + folder.fsName);
    }

    function jsonString(value) {
        return "\"" + String(value).replace(/\\/g, "\\\\").replace(/\"/g, "\\\"")
            .replace(/\r/g, "\\r").replace(/\n/g, "\\n") + "\"";
    }

    function slug(value, fallback) {
        var text = String(value);
        if (text == "><") return "base";
        text = text.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
        return text.length ? text : fallback;
    }

    function addLayers(layers, parentPath, ancestors) {
        for (var i = 0; i < layers.length; i++) {
            var layer = layers[i];
            var path = parentPath.concat([layer.name]);
            var parentRecords = ancestors.slice(0);
            var record = {
                layer: layer,
                path: path,
                visible: layer.visible,
                ancestors: parentRecords
            };
            allLayers.push(record);
            var childAncestors = parentRecords.concat([record]);
            addLayers(layer.layers, path, childAncestors);
        }
    }

    function findRecord(layer) {
        for (var i = 0; i < allLayers.length; i++) {
            if (allLayers[i].layer == layer) return allLayers[i];
        }
        return null;
    }

    function recordIsUnder(record, ancestor) {
        if (record == ancestor) return true;
        for (var i = 0; i < record.ancestors.length; i++) {
            if (record.ancestors[i] == ancestor) return true;
        }
        return false;
    }

    function itemLayer(item) {
        var current = item;
        while (current && current.typename != "Layer") current = current.parent;
        return current;
    }

    function layerAndParentsWereVisible(layer) {
        var current = layer;
        var record = findRecord(current);
        if (!record || !record.visible) return false;
        for (var i = 0; i < record.ancestors.length; i++) {
            if (!record.ancestors[i].visible) return false;
        }
        return true;
    }

    function setLayerVisible(layer, visible) {
        if (layer.visible != visible) layer.visible = visible;
    }

    function setItemHidden(item, hidden) {
        if (item.hidden != hidden) {
            unlockItemAndParents(item);
            item.hidden = hidden;
        }
    }

    function setGroupClipped(group, clipped) {
        unlockItemAndParents(group);
        try {
            if (group.clipped != clipped) group.clipped = clipped;
        } catch (error) {
            throw new Error("Could not change clipping on temporary Illustrator group '" +
                (group.name || "unnamed group") + "': " + error.message);
        }
    }

    function unlockItemAndParents(item) {
        var chain = [];
        var current = item;
        while (current && current.typename != "Document") {
            chain.push(current);
            if (current.typename == "Layer") break;
            current = current.parent;
        }
        for (var i = chain.length - 1; i >= 0; i--) {
            try {
                if (chain[i].locked) chain[i].locked = false;
            } catch (error) {
                var name = "unnamed artwork";
                try { name = chain[i].name || name; } catch (nameError) {}
                throw new Error("Could not unlock temporary Illustrator item '" + name + "': " + error.message);
            }
        }
    }

    function unlockSourceArtwork() {
        for (var i = 0; i < allLayers.length; i++) {
            var layerRecord = allLayers[i];
            try {
                if (layerRecord.layer.locked) layerRecord.layer.locked = false;
            } catch (error) {
                throw new Error("Could not unlock temporary Illustrator layer '" +
                    layerRecord.path.join(" / ") + "': " + error.message);
            }
        }
        for (var j = 0; j < allPageItems.length; j++) {
            unlockItemAndParents(allPageItems[j].item);
        }
    }

    function itemAndParentsWereVisible(item) {
        var current = item;
        while (current && current.typename != "Layer" && current.typename != "Document") {
            var entry = itemRecord(current);
            if (entry && entry.hidden) return false;
            current = current.parent;
        }
        return current && current.typename == "Layer" && layerAndParentsWereVisible(current);
    }

    function includeItem(item) {
        return itemAndParentsWereVisible(item);
    }

    function collectPageItems() {
        for (var i = 0; i < doc.pageItems.length; i++) {
            var item = doc.pageItems[i];
            var hidden = false;
            try { hidden = item.hidden; } catch (e) {}
            allPageItems.push({ item: item, hidden: hidden, sourceVisible: false });
        }
        for (var j = 0; j < allPageItems.length; j++) {
            allPageItems[j].sourceVisible = itemAndParentsWereVisible(allPageItems[j].item);
        }
    }

    function itemRecord(item) {
        for (var i = 0; i < allPageItems.length; i++) {
            if (allPageItems[i].item == item) return allPageItems[i];
        }
        return null;
    }

    function isItemUnder(item, target) {
        var current = item;
        while (current && current.typename != "Layer" && current.typename != "Document") {
            if (current == target) return true;
            current = current.parent;
        }
        return false;
    }

    function isRequiredClipMask(candidate, target) {
        var ancestor = target.parent;
        while (ancestor && ancestor.typename != "Layer" && ancestor.typename != "Document") {
            if (ancestor.typename == "GroupItem" && ancestor.clipped && candidate.parent == ancestor) {
                try { if (candidate.clipping) return true; } catch (e) {}
            }
            ancestor = ancestor.parent;
        }
        return false;
    }

    function isVisibleGroup(group) {
        var current = group;
        while (current && current.typename != "Layer" && current.typename != "Document") {
            try { if (current.hidden) return false; } catch (e) {}
            current = current.parent;
        }
        return layerAndParentsWereVisible(itemLayer(group));
    }

    function countVisibleItemsInLayer(targetRecord) {
        var count = 0;
        for (var i = 0; i < allPageItems.length; i++) {
            var entry = allPageItems[i];
            if (entry.hidden || !includeItem(entry.item)) continue;
            var ownerRecord = findRecord(itemLayer(entry.item));
            if (ownerRecord && recordIsUnder(ownerRecord, targetRecord)) count++;
        }
        return count;
    }

    function countItemsInGroup(group) {
        var count = 0;
        for (var i = 0; i < allPageItems.length; i++) {
            var entry = allPageItems[i];
            if (!entry.hidden && isItemUnder(entry.item, group)) count++;
        }
        return count;
    }

    function groupPath(group) {
        var names = [];
        var current = group;
        while (current && current.typename != "Layer" && current.typename != "Document") {
            if (current.typename == "GroupItem") {
                var name = "";
                try { name = current.name; } catch (e) {}
                names.unshift(name || "Group");
            }
            current = current.parent;
        }
        return names;
    }

    function padNumber(value, width) {
        var text = String(value);
        while (text.length < width) text = "0" + text;
        return text;
    }

    function groupOutputPath(layerRecord, group, index) {
        var names = groupPath(group);
        var folder = new Folder(outputFolder.fsName + "/groups");
        ensureFolder(folder);
        for (var i = 0; i < layerRecord.path.length; i++) {
            folder = new Folder(folder.fsName + "/" + slug(layerRecord.path[i], "layer_" + i));
            ensureFolder(folder);
        }
        for (var j = 0; j < names.length - 1; j++) {
            folder = new Folder(folder.fsName + "/" + slug(names[j], "group"));
            ensureFolder(folder);
        }
        var leafName = names.length ? slug(names[names.length - 1], "group") : "group";
        var filename = "group_" + padNumber(index + 1, 4) + "_" + leafName + ".png";
        var relativeParts = ["groups"];
        for (var k = 0; k < layerRecord.path.length; k++) {
            relativeParts.push(slug(layerRecord.path[k], "layer_" + k));
        }
        for (var m = 0; m < names.length - 1; m++) {
            relativeParts.push(slug(names[m], "group"));
        }
        relativeParts.push(filename);
        return {
            file: new File(folder.fsName + "/" + filename),
            relative: relativeParts.join("/")
        };
    }

    function itemOutputPath(layerRecord, item, index) {
        var names = groupPath(item);
        var folder = new Folder(outputFolder.fsName + "/objects");
        ensureFolder(folder);
        for (var i = 0; i < layerRecord.path.length; i++) {
            folder = new Folder(folder.fsName + "/" + slug(layerRecord.path[i], "layer_" + i));
            ensureFolder(folder);
        }
        for (var j = 0; j < names.length; j++) {
            folder = new Folder(folder.fsName + "/" + slug(names[j], "group"));
            ensureFolder(folder);
        }
        var itemName = "";
        try { itemName = item.name; } catch (e) {}
        var filename = "item_" + padNumber(index + 1, 5) + "_" +
            slug(item.typename, "item") + "_" + slug(itemName, "unnamed") + ".png";
        var relativeParts = ["objects"];
        for (var k = 0; k < layerRecord.path.length; k++) {
            relativeParts.push(slug(layerRecord.path[k], "layer_" + k));
        }
        for (var m = 0; m < names.length; m++) {
            relativeParts.push(slug(names[m], "group"));
        }
        relativeParts.push(filename);
        return {
            file: new File(folder.fsName + "/" + filename),
            relative: relativeParts.join("/")
        };
    }

    function exportPng(file) {
        var options = new ExportOptionsPNG24();
        options.antiAliasing = true;
        options.transparency = true;
        options.artBoardClipping = true;
        options.horizontalScale = (CANVAS_WIDTH / (bounds[2] - bounds[0])) * 100;
        options.verticalScale = (CANVAS_HEIGHT / (bounds[1] - bounds[3])) * 100;
        doc.exportFile(file, ExportType.PNG24, options);
    }

    function isClipMask(item) {
        try { return item.clipping === true; } catch (e) { return false; }
    }

    function exportClipMask(item, file) {
        // A clipping path is intentionally invisible in the Illustrator art.
        // In the temporary copy, turn it into a white filled silhouette so
        // the same aligned export can be used as a runtime alpha mask.
        var parentGroup = item.parent;
        var original = {
            clipping: item.clipping,
            filled: item.filled,
            stroked: item.stroked,
            fillColor: item.fillColor,
            opacity: item.opacity,
            groupClipped: parentGroup.clipped
        };
        var white = new RGBColor();
        white.red = 255;
        white.green = 255;
        white.blue = 255;
        try {
            unlockItemAndParents(parentGroup);
            unlockItemAndParents(item);
            setGroupClipped(parentGroup, false);
            item.clipping = false;
            item.hidden = false;
            item.filled = true;
            item.fillColor = white;
            item.stroked = false;
            item.opacity = 100;
            exportPng(file);
        } finally {
            item.clipping = original.clipping;
            item.filled = original.filled;
            item.stroked = original.stroked;
            item.fillColor = original.fillColor;
            item.opacity = original.opacity;
            setGroupClipped(parentGroup, original.groupClipped);
        }
    }

    function isPupilArtwork(item) {
        var name = "";
        try { name = item.name; } catch (e) {}
        if (name != "Pupil" && name != "Glint") return false;
        var names = groupPath(item);
        for (var i = 0; i < names.length; i++) {
            if (names[i] == "Pupil") return true;
        }
        return false;
    }

    function exportUnmaskedPupil(item, file) {
        // Disable every clipped ancestor in this temporary copy so Illustrator
        // exports the complete pupil disk and shine, then restore the source.
        var clippedGroups = [];
        var clippingItems = [];
        var ancestor = item.parent;
        while (ancestor && ancestor.typename != "Layer" && ancestor.typename != "Document") {
            if (ancestor.typename == "GroupItem" && ancestor.clipped) {
                clippedGroups.push({ group: ancestor, clipped: ancestor.clipped });
                for (var i = 0; i < allPageItems.length; i++) {
                    var entry = allPageItems[i];
                    if (entry.item.parent == ancestor && isClipMask(entry.item)) {
                        clippingItems.push({ item: entry.item, hidden: entry.hidden });
                    }
                }
            }
            ancestor = ancestor.parent;
        }

        try {
            for (var groupIndex = 0; groupIndex < clippedGroups.length; groupIndex++) {
                setGroupClipped(clippedGroups[groupIndex].group, false);
            }
            for (var maskIndex = 0; maskIndex < clippingItems.length; maskIndex++) {
                setItemHidden(clippingItems[maskIndex].item, true);
            }
            exportPng(file);
        } finally {
            for (var restoreGroup = clippedGroups.length - 1; restoreGroup >= 0; restoreGroup--) {
                setGroupClipped(
                    clippedGroups[restoreGroup].group,
                    clippedGroups[restoreGroup].clipped
                );
            }
            for (var restoreMask = clippingItems.length - 1; restoreMask >= 0; restoreMask--) {
                setItemHidden(clippingItems[restoreMask].item, clippingItems[restoreMask].hidden);
            }
        }
    }

    function measureContent() {
        for (var i = 0; i < doc.pageItems.length; i++) {
            var item = doc.pageItems[i];
            if (!includeItem(item)) continue;
            var itemBounds;
            try { itemBounds = item.visibleBounds; } catch (e) { continue; }
            if (!itemBounds || itemBounds.length < 4) continue;
            bounds[0] = Math.min(bounds[0], itemBounds[0]);
            bounds[1] = Math.max(bounds[1], itemBounds[1]);
            bounds[2] = Math.max(bounds[2], itemBounds[2]);
            bounds[3] = Math.min(bounds[3], itemBounds[3]);
        }
        if (!isFinite(bounds[0]) || !isFinite(bounds[1]) || !isFinite(bounds[2]) || !isFinite(bounds[3])) {
            throw new Error("No visible artwork was found in the Illustrator document.");
        }
    }

    function visitVisibleLayers(layers, path, callback) {
        for (var i = 0; i < layers.length; i++) {
            var layer = layers[i];
            var record = findRecord(layer);
            if (!record || !record.visible) continue;
            var nextPath = path.concat([layer.name]);
            callback(layer, nextPath);
            visitVisibleLayers(layer.layers, nextPath, callback);
        }
    }

    function isolateLayer(targetRecord) {
        // Restore the source-visible layer tree before editing its page items.
        for (var i = 0; i < allLayers.length; i++) {
            setLayerVisible(allLayers[i].layer, allLayers[i].visible);
        }

        for (var j = 0; j < allPageItems.length; j++) {
            var entry = allPageItems[j];
            setItemHidden(entry.item, entry.hidden);
            var ownerRecord = findRecord(itemLayer(entry.item));
            if (entry.sourceVisible && (!ownerRecord || !recordIsUnder(ownerRecord, targetRecord))) {
                setItemHidden(entry.item, true);
            }
        }

        for (var k = 0; k < allPageItems.length; k++) {
            var targetItem = allPageItems[k].item;
            var targetOwner = findRecord(itemLayer(targetItem));
            if (!targetOwner || !recordIsUnder(targetOwner, targetRecord) || !allPageItems[k].sourceVisible) continue;
            for (var m = 0; m < allPageItems.length; m++) {
                var possibleMask = allPageItems[m];
                if (isRequiredClipMask(possibleMask.item, targetItem)) {
                    setItemHidden(possibleMask.item, possibleMask.hidden);
                }
            }
        }

        for (var layerIndex = 0; layerIndex < allLayers.length; layerIndex++) {
            var record = allLayers[layerIndex];
            var partOfTargetTree = recordIsUnder(record, targetRecord) ||
                recordIsUnder(targetRecord, record);
            setLayerVisible(record.layer, record.visible && partOfTargetTree);
        }
    }

    function isolateItem(item) {
        var targetLayer = findRecord(itemLayer(item));
        for (var i = 0; i < allLayers.length; i++) {
            setLayerVisible(allLayers[i].layer, allLayers[i].visible);
        }

        for (var j = 0; j < allPageItems.length; j++) {
            var entry = allPageItems[j];
            setItemHidden(entry.item, entry.hidden);
        }
        for (var k = 0; k < allPageItems.length; k++) {
            var candidate = allPageItems[k].item;
            var keep = isItemUnder(candidate, item) || isItemUnder(item, candidate) ||
                isRequiredClipMask(candidate, item);
            if (!keep && allPageItems[k].sourceVisible) setItemHidden(allPageItems[k].item, true);
        }

        for (var layerIndex = 0; layerIndex < allLayers.length; layerIndex++) {
            var record = allLayers[layerIndex];
            setLayerVisible(record.layer, record.visible && recordIsUnder(targetLayer, record));
        }
    }

    function outputPathFor(path) {
        var segments = [];
        for (var i = 0; i < path.length; i++) segments.push(slug(path[i], "layer_" + i));
        var name = segments.pop() + ".png";
        var folder = outputFolder;
        for (var j = 0; j < segments.length; j++) {
            folder = new Folder(folder.fsName + "/" + segments[j]);
            ensureFolder(folder);
        }
        return { file: new File(folder.fsName + "/" + name), relative: segments.concat([name]).join("/") };
    }

    function exportLayer(layer, path) {
        var targetRecord = findRecord(layer);
        isolateLayer(targetRecord);
        var output = outputPathFor(path);
        var options = new ExportOptionsPNG24();
        options.antiAliasing = true;
        options.transparency = true;
        options.artBoardClipping = true;
        options.horizontalScale = (CANVAS_WIDTH / (bounds[2] - bounds[0])) * 100;
        options.verticalScale = (CANVAS_HEIGHT / (bounds[1] - bounds[3])) * 100;
        doc.exportFile(output.file, ExportType.PNG24, options);

        exportEntries.push({
            path: path,
            file: output.relative,
            visible: true,
            page_item_count: countVisibleItemsInLayer(targetRecord)
        });
    }

    function exportGroup(group, index) {
        var ownerRecord = findRecord(itemLayer(group));
        isolateItem(group);
        var output = groupOutputPath(ownerRecord, group, index);
        var options = new ExportOptionsPNG24();
        options.antiAliasing = true;
        options.transparency = true;
        options.artBoardClipping = true;
        options.horizontalScale = (CANVAS_WIDTH / (bounds[2] - bounds[0])) * 100;
        options.verticalScale = (CANVAS_HEIGHT / (bounds[1] - bounds[3])) * 100;
        doc.exportFile(output.file, ExportType.PNG24, options);

        groupEntries.push({
            layer_path: ownerRecord.path,
            group_path: groupPath(group),
            file: output.relative,
            page_item_count: countItemsInGroup(group)
        });
    }

    function exportObject(item, index) {
        var ownerRecord = findRecord(itemLayer(item));
        isolateItem(item);
        var output = itemOutputPath(ownerRecord, item, index);
        var clipMask = isClipMask(item);
        var unmaskedPupil = isPupilArtwork(item);
        if (clipMask) exportClipMask(item, output.file);
        else if (unmaskedPupil) exportUnmaskedPupil(item, output.file);
        else exportPng(output.file);

        var itemName = "";
        try { itemName = item.name; } catch (e) {}
        objectEntries.push({
            layer_path: ownerRecord.path,
            group_path: groupPath(item),
            item_type: item.typename,
            item_name: itemName,
            is_clip_mask: clipMask,
            is_unmasked_pupil: unmaskedPupil,
            file: output.relative
        });
    }

    function writeManifest() {
        var file = new File(outputFolder.fsName + "/manifest.json");
        file.encoding = "UTF-8";
        if (!file.open("w")) throw new Error("Could not write manifest: " + file.fsName);
        file.write("{\n  \"source_file\": " + jsonString(sourceFile.name) + ",\n");
        file.write("  \"canvas_size\": [" + CANVAS_WIDTH + ", " + CANVAS_HEIGHT + "],\n");
        file.write("  \"content_bounds_points\": [" + bounds.join(", ") + "],\n");
        file.write("  \"exports\": [\n");
        for (var i = 0; i < exportEntries.length; i++) {
            var entry = exportEntries[i];
            file.write("    {\"path\": [");
            for (var j = 0; j < entry.path.length; j++) {
                if (j) file.write(", ");
                file.write(jsonString(entry.path[j]));
            }
            file.write("], \"file\": " + jsonString(entry.file) +
                ", \"page_item_count\": " + entry.page_item_count + "}");
            file.write(i + 1 == exportEntries.length ? "\n" : ",\n");
        }
        file.write("  ],\n  \"group_exports\": [\n");
        for (var k = 0; k < groupEntries.length; k++) {
            var groupEntry = groupEntries[k];
            file.write("    {\"layer_path\": [");
            for (var m = 0; m < groupEntry.layer_path.length; m++) {
                if (m) file.write(", ");
                file.write(jsonString(groupEntry.layer_path[m]));
            }
            file.write("], \"group_path\": [");
            for (var n = 0; n < groupEntry.group_path.length; n++) {
                if (n) file.write(", ");
                file.write(jsonString(groupEntry.group_path[n]));
            }
            file.write("], \"file\": " + jsonString(groupEntry.file) +
                ", \"page_item_count\": " + groupEntry.page_item_count + "}");
            file.write(k + 1 == groupEntries.length ? "\n" : ",\n");
        }
        file.write("  ],\n  \"object_exports\": [\n");
        for (var p = 0; p < objectEntries.length; p++) {
            var objectEntry = objectEntries[p];
            file.write("    {\"layer_path\": [");
            for (var q = 0; q < objectEntry.layer_path.length; q++) {
                if (q) file.write(", ");
                file.write(jsonString(objectEntry.layer_path[q]));
            }
            file.write("], \"group_path\": [");
            for (var r = 0; r < objectEntry.group_path.length; r++) {
                if (r) file.write(", ");
                file.write(jsonString(objectEntry.group_path[r]));
            }
            file.write("], \"item_type\": " + jsonString(objectEntry.item_type) +
                ", \"item_name\": " + jsonString(objectEntry.item_name) +
                ", \"is_clip_mask\": " + (objectEntry.is_clip_mask ? "true" : "false") +
                ", \"is_unmasked_pupil\": " + (objectEntry.is_unmasked_pupil ? "true" : "false") +
                ", \"file\": " + jsonString(objectEntry.file) + "}");
            file.write(p + 1 == objectEntries.length ? "\n" : ",\n");
        }
        file.write("  ]\n}\n");
        file.close();
    }

    try {
        if (!sourceFile.exists) throw new Error("Source Illustrator file not found: " + sourceFile.fsName);
        ensureFolder(outputFolder);
        if (!sourceFile.copy(workingCopy.fsName)) throw new Error("Could not create a temporary Illustrator copy.");

        app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS;
        doc = app.open(workingCopy);
        addLayers(doc.layers, [], []);
        collectPageItems();
        unlockSourceArtwork();
        measureContent();

        var artboard = doc.artboards.add(bounds);
        doc.artboards.setActiveArtboardIndex(doc.artboards.length - 1);
        visitVisibleLayers(doc.layers, [], function (layer, path) {
            exportLayer(layer, path);
        });

        for (var groupIndex = 0; groupIndex < allPageItems.length; groupIndex++) {
            var group = allPageItems[groupIndex].item;
            if (group.typename == "GroupItem" && isVisibleGroup(group)) visibleGroups.push(group);
        }
        for (var exportGroupIndex = 0; exportGroupIndex < visibleGroups.length; exportGroupIndex++) {
            exportGroup(visibleGroups[exportGroupIndex], exportGroupIndex);
        }

        for (var objectIndex = 0; objectIndex < allPageItems.length; objectIndex++) {
            var objectItem = allPageItems[objectIndex].item;
            if (objectItem.typename == "GroupItem" || !includeItem(objectItem)) continue;
            visibleObjects.push({ item: objectItem, index: objectIndex });
        }
        for (var exportObjectIndex = 0; exportObjectIndex < visibleObjects.length; exportObjectIndex++) {
            var objectRecord = visibleObjects[exportObjectIndex];
            exportObject(objectRecord.item, objectRecord.index);
        }

        writeManifest();
        doc.close(SaveOptions.DONOTSAVECHANGES);
        doc = null;
        workingCopy.remove();
        app.userInteractionLevel = oldInteractionLevel;
        alert("Exported " + exportEntries.length + " visible Illustrator layers and sublayers, " +
            groupEntries.length + " artwork groups, and " + objectEntries.length +
            " individual artwork objects to:\n" + outputFolder.fsName);
    } catch (error) {
        try { if (doc) doc.close(SaveOptions.DONOTSAVECHANGES); } catch (closeError) {}
        try { if (workingCopy.exists) workingCopy.remove(); } catch (removeError) {}
        app.userInteractionLevel = oldInteractionLevel;
        alert("Illustrator layer export failed:\n" + error.message + (error.line ? "\nLine: " + error.line : ""));
    }
}());
