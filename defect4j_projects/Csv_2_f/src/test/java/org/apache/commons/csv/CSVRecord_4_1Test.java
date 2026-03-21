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

class CSVRecord_4_1Test {

    @Test
    @Timeout(8000)
    void testIsConsistent_mappingNull() throws Exception {
        String[] values = new String[] {"a", "b", "c"};
        Map<String, Integer> mapping = null;

        Constructor<CSVRecord> constructor = CSVRecord.class.getDeclaredConstructor(String[].class, Map.class, String.class, long.class);
        constructor.setAccessible(true);
        CSVRecord record = constructor.newInstance((Object) values, mapping, null, 1L);

        Method isConsistentMethod = CSVRecord.class.getDeclaredMethod("isConsistent");
        isConsistentMethod.setAccessible(true);
        boolean result = (boolean) isConsistentMethod.invoke(record);

        assertTrue(result, "When mapping is null, isConsistent should return true");
    }

    @Test
    @Timeout(8000)
    void testIsConsistent_mappingSizeEqualsValuesLength() throws Exception {
        String[] values = new String[] {"a", "b", "c"};
        Map<String, Integer> mapping = new HashMap<>();
        mapping.put("col1", 0);
        mapping.put("col2", 1);
        mapping.put("col3", 2);

        Constructor<CSVRecord> constructor = CSVRecord.class.getDeclaredConstructor(String[].class, Map.class, String.class, long.class);
        constructor.setAccessible(true);
        CSVRecord record = constructor.newInstance((Object) values, mapping, null, 1L);

        Method isConsistentMethod = CSVRecord.class.getDeclaredMethod("isConsistent");
        isConsistentMethod.setAccessible(true);
        boolean result = (boolean) isConsistentMethod.invoke(record);

        assertTrue(result, "When mapping size equals values length, isConsistent should return true");
    }

    @Test
    @Timeout(8000)
    void testIsConsistent_mappingSizeNotEqualsValuesLength() throws Exception {
        String[] values = new String[] {"a", "b", "c"};
        Map<String, Integer> mapping = new HashMap<>();
        mapping.put("col1", 0);
        mapping.put("col2", 1);
        // mapping size is 2, values length is 3

        Constructor<CSVRecord> constructor = CSVRecord.class.getDeclaredConstructor(String[].class, Map.class, String.class, long.class);
        constructor.setAccessible(true);
        CSVRecord record = constructor.newInstance((Object) values, mapping, null, 1L);

        Method isConsistentMethod = CSVRecord.class.getDeclaredMethod("isConsistent");
        isConsistentMethod.setAccessible(true);
        boolean result = (boolean) isConsistentMethod.invoke(record);

        assertFalse(result, "When mapping size does not equal values length, isConsistent should return false");
    }
}