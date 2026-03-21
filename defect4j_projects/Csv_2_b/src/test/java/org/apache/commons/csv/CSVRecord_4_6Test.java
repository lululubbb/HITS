package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Iterator;

import static org.junit.jupiter.api.Assertions.*;

import java.lang.reflect.Constructor;
import java.lang.reflect.Method;
import java.util.HashMap;
import java.util.Map;

import org.junit.jupiter.api.Test;

class CSVRecord_4_6Test {

    private CSVRecord createCSVRecord(String[] values, Map<String, Integer> mapping) throws Exception {
        Constructor<CSVRecord> constructor = CSVRecord.class.getDeclaredConstructor(String[].class, Map.class, String.class, long.class);
        constructor.setAccessible(true);
        return constructor.newInstance(values, mapping, null, 1L);
    }

    @Test
    @Timeout(8000)
    void testIsConsistent_mappingNull() throws Exception {
        // mapping is null, should return true
        String[] values = new String[] {"a", "b"};
        Map<String, Integer> mapping = null;
        CSVRecord record = createCSVRecord(values, mapping);

        Method isConsistentMethod = CSVRecord.class.getDeclaredMethod("isConsistent");
        isConsistentMethod.setAccessible(true);
        boolean result = (boolean) isConsistentMethod.invoke(record);

        assertTrue(result);
    }

    @Test
    @Timeout(8000)
    void testIsConsistent_mappingSizeEqualsValuesLength() throws Exception {
        // mapping size == values.length, should return true
        String[] values = new String[] {"a", "b", "c"};
        Map<String, Integer> mapping = new HashMap<>();
        mapping.put("one", 0);
        mapping.put("two", 1);
        mapping.put("three", 2);
        CSVRecord record = createCSVRecord(values, mapping);

        Method isConsistentMethod = CSVRecord.class.getDeclaredMethod("isConsistent");
        isConsistentMethod.setAccessible(true);
        boolean result = (boolean) isConsistentMethod.invoke(record);

        assertTrue(result);
    }

    @Test
    @Timeout(8000)
    void testIsConsistent_mappingSizeNotEqualsValuesLength() throws Exception {
        // mapping size != values.length, should return false
        String[] values = new String[] {"a", "b", "c"};
        Map<String, Integer> mapping = new HashMap<>();
        mapping.put("one", 0);
        mapping.put("two", 1);
        // mapping size is 2, values length is 3
        CSVRecord record = createCSVRecord(values, mapping);

        Method isConsistentMethod = CSVRecord.class.getDeclaredMethod("isConsistent");
        isConsistentMethod.setAccessible(true);
        boolean result = (boolean) isConsistentMethod.invoke(record);

        assertFalse(result);
    }
}