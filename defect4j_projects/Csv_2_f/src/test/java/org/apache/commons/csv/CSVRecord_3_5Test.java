package org.apache.commons.csv;
import org.junit.jupiter.api.Timeout;
import java.io.Serializable;
import java.util.Arrays;
import java.util.Iterator;
import static org.junit.jupiter.api.Assertions.*;

import java.lang.reflect.Constructor;
import java.util.HashMap;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

public class CSVRecord_3_5Test {

    private Map<String, Integer> mapping;
    private String[] values;
    private CSVRecord record;

    @BeforeEach
    public void setUp() {
        mapping = new HashMap<>();
        mapping.put("header1", 0);
        mapping.put("header2", 1);
        values = new String[] {"value1", "value2"};
        record = new CSVRecord(values, mapping, null, 1L);
    }

    @Test
    @Timeout(8000)
    public void testGet_WithValidName_ReturnsValue() {
        assertEquals("value1", record.get("header1"));
        assertEquals("value2", record.get("header2"));
    }

    @Test
    @Timeout(8000)
    public void testGet_WithNameNotInMapping_ReturnsNull() {
        assertNull(record.get("header3"));
    }

    @Test
    @Timeout(8000)
    public void testGet_WithNullMapping_ThrowsIllegalStateException() throws Exception {
        // Create CSVRecord with null mapping using reflection because constructor is package-private
        String[] vals = new String[] {"val1"};
        CSVRecord recordWithNullMapping = createCSVRecord(vals, null, null, 1L);

        IllegalStateException thrown = assertThrows(IllegalStateException.class, () -> {
            recordWithNullMapping.get("any");
        });
        assertEquals("No header mapping was specified, the record values can't be accessed by name", thrown.getMessage());
    }

    @SuppressWarnings("unchecked")
    private CSVRecord createCSVRecord(String[] values, Map<String, Integer> mapping, String comment, long recordNumber) throws Exception {
        Class<?> clazz = Class.forName("org.apache.commons.csv.CSVRecord");
        Constructor<?> ctor = clazz.getDeclaredConstructor(String[].class, Map.class, String.class, long.class);
        ctor.setAccessible(true);
        // Wrap values array in Object[] to avoid varargs ambiguity
        return (CSVRecord) ctor.newInstance(new Object[] {values, mapping, comment, recordNumber});
    }
}