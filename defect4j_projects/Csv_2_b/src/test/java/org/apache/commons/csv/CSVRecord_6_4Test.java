package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Iterator;

import static org.junit.jupiter.api.Assertions.*;

import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.util.HashMap;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class CSVRecord_6_4Test {

    private CSVRecord csvRecord;
    private Map<String, Integer> mapping;
    private String[] values;

    @BeforeEach
    void setUp() throws Exception {
        values = new String[] {"value0", "value1", "value2"};
        mapping = new HashMap<>();
        mapping.put("key0", 0);
        mapping.put("key1", 1);
        mapping.put("key2", 2);

        // Create instance by reflection of constructor
        Constructor<CSVRecord> constructor = CSVRecord.class.getDeclaredConstructor(String[].class, Map.class, String.class, long.class);
        constructor.setAccessible(true);
        csvRecord = constructor.newInstance(values, mapping, "comment", 1L);
    }

    @Test
    @Timeout(8000)
    void testIsSet_MappedAndIndexInBounds() {
        assertTrue(csvRecord.isSet("key0"));
        assertTrue(csvRecord.isSet("key1"));
        assertTrue(csvRecord.isSet("key2"));
    }

    @Test
    @Timeout(8000)
    void testIsSet_MappedButIndexOutOfBounds() throws Exception {
        mapping.put("keyOutOfBounds", 3);
        // Update the mapping field in csvRecord
        Field mappingField = CSVRecord.class.getDeclaredField("mapping");
        mappingField.setAccessible(true);
        mappingField.set(csvRecord, mapping);

        assertFalse(csvRecord.isSet("keyOutOfBounds"));
    }

    @Test
    @Timeout(8000)
    void testIsSet_NotMapped() {
        assertFalse(csvRecord.isSet("notMapped"));
    }

    @Test
    @Timeout(8000)
    void testIsSet_UsingReflection() throws Exception {
        Method isSetMethod = CSVRecord.class.getDeclaredMethod("isSet", String.class);
        isSetMethod.setAccessible(true);

        assertTrue((Boolean) isSetMethod.invoke(csvRecord, "key0"));
        assertFalse((Boolean) isSetMethod.invoke(csvRecord, "notMapped"));

        mapping.put("keyOutOfBounds", 5);
        Field mappingField = CSVRecord.class.getDeclaredField("mapping");
        mappingField.setAccessible(true);
        mappingField.set(csvRecord, mapping);

        assertFalse((Boolean) isSetMethod.invoke(csvRecord, "keyOutOfBounds"));
    }
}