package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Iterator;

import static org.junit.jupiter.api.Assertions.*;

import java.lang.reflect.Constructor;
import java.lang.reflect.InvocationTargetException;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class CSVRecord_3_6Test {

    private Constructor<CSVRecord> constructor;

    @BeforeEach
    void setUp() throws NoSuchMethodException, SecurityException {
        constructor = CSVRecord.class.getDeclaredConstructor(String[].class, Map.class, String.class, long.class);
        constructor.setAccessible(true);
    }

    @Test
    @Timeout(8000)
    void testGetWithMappingNullThrows() throws InstantiationException, IllegalAccessException, IllegalArgumentException, InvocationTargetException {
        CSVRecord record = constructor.newInstance(new Object[]{new String[]{"a", "b"}, null, null, 1L});
        IllegalStateException thrown = assertThrows(IllegalStateException.class, () -> record.get("any"));
        assertEquals("No header mapping was specified, the record values can't be accessed by name", thrown.getMessage());
    }

    @Test
    @Timeout(8000)
    void testGetWithNameMappedReturnsValue() throws InstantiationException, IllegalAccessException, IllegalArgumentException, InvocationTargetException {
        Map<String, Integer> mapping = new HashMap<>();
        mapping.put("key1", 0);
        mapping.put("key2", 1);
        String[] values = new String[]{"val1", "val2"};
        CSVRecord record = constructor.newInstance(new Object[]{values, mapping, null, 1L});

        assertEquals("val1", record.get("key1"));
        assertEquals("val2", record.get("key2"));
    }

    @Test
    @Timeout(8000)
    void testGetWithNameNotMappedReturnsNull() throws InstantiationException, IllegalAccessException, IllegalArgumentException, InvocationTargetException {
        Map<String, Integer> mapping = Collections.singletonMap("key1", 0);
        String[] values = new String[]{"val1"};
        CSVRecord record = constructor.newInstance(new Object[]{values, mapping, null, 1L});

        assertNull(record.get("nonexistent"));
    }
}