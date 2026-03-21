package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Iterator;

import static org.junit.jupiter.api.Assertions.*;

import java.lang.reflect.Method;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class CSVRecord_6_6Test {

    private CSVRecord csvRecord;
    private Map<String, Integer> mapping;
    private String[] values;

    @BeforeEach
    void setUp() {
        values = new String[] { "value0", "value1", "value2" };
        mapping = new HashMap<>();
        mapping.put("col0", 0);
        mapping.put("col1", 1);
        mapping.put("col2", 2);
        csvRecord = new CSVRecord(values, mapping, null, 1L);
    }

    @Test
    @Timeout(8000)
    void testIsSet_MappedAndIndexInRange() {
        assertTrue(csvRecord.isSet("col0"));
        assertTrue(csvRecord.isSet("col1"));
        assertTrue(csvRecord.isSet("col2"));
    }

    @Test
    @Timeout(8000)
    void testIsSet_MappedButIndexOutOfRange() {
        Map<String, Integer> newMapping = new HashMap<>(mapping);
        newMapping.put("col3", 3);
        CSVRecord recordWithExtraMapping = new CSVRecord(values, newMapping, null, 1L);
        assertFalse(recordWithExtraMapping.isSet("col3"));
    }

    @Test
    @Timeout(8000)
    void testIsSet_NotMapped() {
        assertFalse(csvRecord.isSet("nonexistent"));
    }

    @Test
    @Timeout(8000)
    void testIsSet_EmptyMapping() {
        CSVRecord emptyMappingRecord = new CSVRecord(values, Collections.emptyMap(), null, 1L);
        assertFalse(emptyMappingRecord.isSet("any"));
    }

    @Test
    @Timeout(8000)
    void testIsSet_EmptyValuesArray() {
        Map<String, Integer> map = new HashMap<>();
        map.put("col0", 0);
        CSVRecord emptyValuesRecord = new CSVRecord(new String[0], map, null, 1L);
        assertFalse(emptyValuesRecord.isSet("col0"));
    }

    @Test
    @Timeout(8000)
    void testIsSet_PrivateMethodViaReflection() throws Exception {
        Method isSetMethod = CSVRecord.class.getDeclaredMethod("isSet", String.class);
        isSetMethod.setAccessible(true);
        boolean result = (boolean) isSetMethod.invoke(csvRecord, "col1");
        assertTrue(result);

        result = (boolean) isSetMethod.invoke(csvRecord, "nonexistent");
        assertFalse(result);
    }
}