package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Iterator;

import static org.junit.jupiter.api.Assertions.*;

import java.lang.reflect.Constructor;
import java.util.HashMap;
import java.util.Map;

import org.junit.jupiter.api.Test;

class CSVRecord_4_5Test {

    @Test
    @Timeout(8000)
    void testIsConsistent_mappingNull_returnsTrue() throws Exception {
        CSVRecord csvRecord = createCSVRecord(null, new String[]{"a", "b"});
        assertTrue(csvRecord.isConsistent());
    }

    @Test
    @Timeout(8000)
    void testIsConsistent_mappingSizeEqualsValuesLength_returnsTrue() throws Exception {
        Map<String, Integer> mapping = new HashMap<>();
        mapping.put("col1", 0);
        mapping.put("col2", 1);
        String[] values = new String[]{"val1", "val2"};
        CSVRecord csvRecord = createCSVRecord(mapping, values);
        assertTrue(csvRecord.isConsistent());
    }

    @Test
    @Timeout(8000)
    void testIsConsistent_mappingSizeNotEqualsValuesLength_returnsFalse() throws Exception {
        Map<String, Integer> mapping = new HashMap<>();
        mapping.put("col1", 0);
        String[] values = new String[]{"val1", "val2"};
        CSVRecord csvRecord = createCSVRecord(mapping, values);
        assertFalse(csvRecord.isConsistent());
    }

    @SuppressWarnings("unchecked")
    private CSVRecord createCSVRecord(Map<String, Integer> mapping, String[] values) throws Exception {
        Constructor<CSVRecord> constructor = CSVRecord.class.getDeclaredConstructor(
                String[].class, Map.class, String.class, long.class);
        constructor.setAccessible(true);
        return constructor.newInstance(values, mapping, null, 0L);
    }
}